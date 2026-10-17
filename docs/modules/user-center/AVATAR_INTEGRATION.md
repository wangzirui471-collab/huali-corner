# U02 头像接线合同

2026-10-17。B 已编写领域代码与测试源码；本机未创建数据库、未运行本阶段测试。
公共入口仍由 A 修改。此合同补充 INTEGRATION.md 的 U01 接线要求。

## 资源与迁移

继续调用 `migrate_account(c)`。新增 `user_avatar_uploads(upload_id,user_id,path,digest,created_at)` 表，
不改原六列 uploads 表，不向它插入头像记录。原商品/证据图查询找不到头像，不能复用头像作为凭证或商品图。
头像文件仍放在既有数据根 `uploads/ua_<32位小写十六进制>.webp`。
表内 path 保存 `uploads/ua_<id>.webp` 形式的相对路径，换数据根恢复时不必改写旧磁盘路径。
路径只取 Market.root，不新增项目根推导；客户端不得提交路径或外链。

UserProfiles 新增 `user_profile_projection(connection,row)`，在同一连接上生成当前可公开头像的 DTO。
资料更新、旧接口更新和头像选择都返回该投影，不互相递归。

## 装配

A 在 Market 增加 `from .account.avatars import UserAvatars`，把它加入组合基类。
UserAvatars 无构造函数、不覆盖认证方法，要求 UserProfiles 也已组合。

| 方法 | 输入与输出 |
| --- | --- |
| user_upload_avatar(actor_id, content: bytes) | 原始图片字节；返回 `{upload_id, preview_url}`，不递增资料版本 |
| user_set_avatar(actor_id, upload_id, profile_version) | 当前会话主体；upload_id 为头像标识或 null；返回资料 DTO 并递增版本 |
| user_is_public_avatar(upload_id) | 仅当前选中、账号启用、资源/文件有效时为 true |
| user_avatar_bytes(actor_id或None, upload_id) | 当前公开头像任何人可读；其他仅启用的所有者可读；返回 bytes，不返回本机路径 |
| user_avatar_backup_entries(snapshot连接) | 从同一个数据库备份快照返回 `(实际Path, ZIP内相对文件名)` 列表，含未选中历史头像 |

## HTTP 解析

头像上传沿用 JSON Base64，但使用专用 `/api/user/avatar/upload`。
在通用 POST 读取 body **之前**，对该路由增加 Content-Length 上限：

```python
# MAX_AVATAR_BYTES = 2 * 1024 * 1024
avatar_json_limit = 4 * ((MAX_AVATAR_BYTES + 2) // 3) + 65536
```

上限必须在 `self.rfile.read(length)` 前检查，仍保留原通用8MiB上限和限速。
请求必须恰好只有 content，一个字符串；编码字符长度不能超过 `4*((MAX_AVATAR_BYTES+2)//3)`，
用 `base64.b64decode(value, validate=True)` 严格解码，解码后再确认 `0<len(content)<=MAX_AVATAR_BYTES`。
拒绝 owner、path、angle 等额外字段；二进制校验由领域函数完成。

在 `u=self.uid()` 之后增加：

```python
if p == '/api/user/avatar/upload' and method == 'POST':
    # 上述 body 长度、白名单、类型与严格解码检查由 A 放在这里及读取前。
    return self.respond(m.user_upload_avatar(u, content))
if p == '/api/user/avatar' and method == 'POST':
    m.require(set(data) == {'upload_id', 'profile_version'}, '头像参数不合法')
    return self.respond(m.user_set_avatar(u, data['upload_id'], data['profile_version']))
```

普通 `/api/upload` 不扩大用途；仍不接受 avatar 角度。

## 媒体授权优先分流

必须在原 `if p.startswith('/media/')` 的 uploads 查询**之前**插入头像分流：

```python
if p.startswith('/media/ua_'):
    fid = p.split('/')[-1]
    return self.respond(m.user_avatar_bytes(self.optional_user(), fid), kind='image/webp')
```

不能先查原 uploads，否则所有头像都404；也不能走原证据图或客服授权，否则会扩大头像预览权限。
该分支的完整授权在 user_avatar_bytes 内完成；别仅以 is_public 判定后再无条件读文件。
保留 respond 原有 no-store、nosniff 及同源策略。不用查询参数传 Token。
网页通过捕获会话的 Bearer 请求读取未公开预览，当前公开头像可直接作为 img 地址。

## 内容与失败处理

- 原文件≤2MiB；JPEG/PNG/WebP真实解码，≤1600万像素，拒绝损坏、SVG、动画和多帧。
- 解码前检查尺寸；不改变全局 Pillow MAX_IMAGE_PIXELS；校正EXIF方向。
- 生成最长边512的全新静态WebP画布，原EXIF/GPS/ICC元数据不复制。
- 上传先处理图片、写专用文件，再在写事务内复核启用状态并登记；失败只补偿删除本次新建文件。
- 选择头像使用同一 profile_version，核对所有者、专用记录和规范路径/实际文件。
- 更换/移除不删除历史资源，但旧资源不再公开。资料 DTO 对失效引用回退为 null，不公开未知路径。
- 暂不物理清理历史头像，避免误删合法记录；该策略没有新增定时任务。

## A 的备份接入（不能遗漏）

现有 ops/service.py 的 `_write_backup` 只从旧 uploads 表收集文件。
A 须在其 `with closing(sqlite3.connect(dbpath)) as snapshot:` 内调用
`avatar_entries = self.user_avatar_backup_entries(snapshot)`；退出快照连接前完成清单读取。
之后与原 uploads 列表一起写入同一个 ZIP，并更新 manifest 的 files 数量。
不要改成从另一个 live 连接读取头像清单，否则可能与备份数据库不一致。

每项直接 `archive.write(path, relative_name)`；不跳过损坏/缺失文件伪称完整备份。
恢复仍沿原流程解压到新空目录，头像相对路径由新数据根解析，保持私有/公开选中关系。
这是 A 所有的 ops 公共接线，B 未修改该模块；未接入前，不能宣称新头像已进入完整备份。

## A/用户待运行

`python -m unittest discover -s tests -p test_user_avatars.py -v`。
测试源码覆盖格式、大小/像素、多帧、元数据、匿名预览/客服越权、选择替换/移除、跨用户、
商品/证据资源隔离、版本冲突、停用账号、缺文件/外部路径和事务失败的文件补偿。
还包括空文件一致性、备份快照清单及换数据根后的头像读取。
再做真实 HTTP 测试：超大 Content-Length 应在读 body 前拒绝，Base64严格解码、公开/私有媒体、
旧 uploads 接口仍可发布商品与工单证据，U01/旧客户端资料保存仍带当前头像。

以上为待执行清单；B 未在本机运行，不把代码审查当作媒体授权或图像安全测试通过。
