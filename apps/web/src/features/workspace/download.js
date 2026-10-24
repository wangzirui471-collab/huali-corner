import { session, clearSession } from '@/shared/legacy/session.js';
/** 下载受控运维结果：只允许已有同源接口，不把私密备份变成公开资源。 @param {'audit'|'backup'} kind 下载种类。 @param {string} [query] 审计筛选。 @param {AbortSignal} [signal] 页面取消。 */
export async function downloadOperation(kind, query = '', signal) {
  const token = session.token;
  const response = await fetch(
    kind === 'audit' ? '/api/audit/export' + (query ? '?' + query : '') : '/api/backup',
    {
      signal,
      method: kind === 'backup' ? 'POST' : 'GET',
      headers: {
        Authorization: 'Bearer ' + token,
        ...(kind === 'backup' ? { 'Content-Type': 'application/json' } : {}),
      },
      body: kind === 'backup' ? '{}' : undefined,
      redirect: 'error',
      credentials: 'same-origin',
      cache: 'no-store',
    },
  );
  if (signal?.aborted || session.token !== token)
    throw new DOMException('账号已切换', 'AbortError');
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('json')) {
    const result = await response.json();
    if (signal?.aborted || session.token !== token)
      throw new DOMException('账号已切换', 'AbortError');
    if (!response.ok) {
      if (response.status === 401) clearSession();
      throw new Error(typeof result.error === 'string' ? result.error : '服务端拒绝下载');
    }
    // 本地旧服务保存到其私密目录，不将服务器路径拼成公开链接。
    return (
      '服务端已生成备份，请在该电脑受控目录核对：' +
      String(result.path || result.backup || JSON.stringify(result))
    );
  }
  if (
    !response.ok ||
    !(kind === 'audit' ? /text\/csv|application\/csv/ : /application\/zip/).test(contentType)
  )
    throw new Error('下载响应不是预期文件，请核对后端日志');
  const blob = await response.blob();
  if (signal?.aborted || session.token !== token)
    throw new DOMException('账号已切换', 'AbortError');
  const url = URL.createObjectURL(blob),
    link = document.createElement('a');
  try {
    link.href = url;
    link.download = `华立转角-${kind}-${new Date().toISOString().slice(0, 10)}.${kind === 'audit' ? 'csv' : 'zip'}`;
    document.body.append(link);
    link.click();
  } finally {
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return '文件已交给浏览器下载，请保存在受控位置；备份成功仍需单独恢复演练。';
}
