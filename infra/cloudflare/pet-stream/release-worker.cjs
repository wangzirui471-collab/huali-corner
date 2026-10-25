/** 基于已核验的线上原字节快照发布宠物切片；plan只本机生成清单，upload不切流量，activate与rollback单独执行。认证只留内存。 */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '../../..');
const stage = path.join(root, 'artifacts/pet-stream-stage');
const dist = path.join(root, 'apps/web/dist-trial');
const snapshot = path.join(root, '.local-config/live-worker-5e7bd074');
const account = '824c84ca5e382e2b4f8de6260d6b0017';
const original = '5e7bd074-0fe4-42ba-887a-2f5347a7479e';
const apiRoot = `https://api.cloudflare.com/client/v4/accounts/${account}`;
const scriptPath = '/workers/scripts/zhuanjiao';
const receiptPath = path.join(stage, 'upload-receipt.json');
let oauth;
/** 读取JSON文件，发布状态只写无秘密的摘要和版本标识。 */
function read(file) { return JSON.parse(fs.readFileSync(file, 'utf8')); }
/** 固定算法摘要用于防止验证后候选内容漂移。 */
function sha(bytes) { return crypto.createHash('sha256').update(bytes).digest('hex'); }
/** 所有断言失败即停止，禁止默认继承意外的新版本。 */
function requireValue(value, message) { if (!value) throw new Error(message); }
/** MIME由自身文件扩展名决定，绝不把JS当HTML下发。 */
function mime(file) { return ({'.html':'text/html;charset=utf-8','.js':'application/javascript;charset=utf-8','.css':'text/css;charset=utf-8','.json':'application/json','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp','.jpg':'image/jpeg','.ico':'image/x-icon','.woff2':'font/woff2','.md':'text/markdown;charset=utf-8'})[path.extname(file)] || 'application/octet-stream'; }
/** 只允许发布dist内普通文件，不跟随符号链接、不上传配置/源码映射或私有数据库。 */
function files(dir, prefix='') { return fs.readdirSync(dir, {withFileTypes:true}).flatMap(entry => { requireValue(!entry.isSymbolicLink(), '发布目录不允许符号链接'); const name=prefix+entry.name; requireValue(!/(^|\/)\.|\.(?:map|sql|db|sqlite|toml|py)$/i.test(name), 'dist含禁止发布文件'); return entry.isDirectory()? files(path.join(dir,entry.name),name+'/') : [name]; }); }
/** 逐模块复核已登记SHA和允许变更集合，并构建静态资源摘要清单。 */
function plan() {
 const manifest=read(path.join(stage,'stream-stage-manifest.json'));
 requireValue(manifest.source_version===original && manifest.source_modules===218 && manifest.unchanged===216 && manifest.modules.length===220,'模块基线或数量不匹配');
 requireValue(JSON.stringify(manifest.changed)===JSON.stringify(['app/cloudflare/ai_support.py','worker.py']) && JSON.stringify(manifest.added)===JSON.stringify(['app/cloudflare/pet_stream_core.py','app/cloudflare/pet_stream_runtime.py']),'变更越过允许范围');
 const old=read(path.join(snapshot,'module-manifest.json'));const oldEntries=Array.isArray(old)?old:old.modules;requireValue(oldEntries?.length===218,'原备份清单异常');const oldByName=new Map(oldEntries.map(m=>[m.name,m]));
 for(const module of manifest.modules){const full=path.resolve(stage,'modules',module.name);requireValue(full.startsWith(path.join(stage,'modules')+path.sep),'模块路径越界');const bytes=fs.readFileSync(full);requireValue(sha(bytes)===module.sha256 && bytes.length===module.bytes,'模块摘要漂移：'+module.name);if(!manifest.changed.includes(module.name)&&!manifest.added.includes(module.name))requireValue(oldByName.get(module.name)?.sha256===module.sha256,'原模块被替换：'+module.name);}
 const assets={};for(const name of files(dist).sort()){const bytes=fs.readFileSync(path.join(dist,name));assets['/'+name]={hash:sha(bytes.toString('base64')+path.extname(name).slice(1)).slice(0,32),size:bytes.length,sha256:sha(bytes),type:mime(name)};}
 requireValue(assets['/index.html']&&assets['/legacy-ai.html']&&assets['/legacy-runtime/src/main.js'],'前端或原AI完整入口缺失');
 const index=fs.readFileSync(path.join(dist,'index.html'),'utf8');requireValue(index.includes('/assets/index-')&&!index.includes('/src/main.js'),'前端不是已构建Vue');
 const report={original,sourceModules:218,unchangedModules:216,changedModules:manifest.changed,addedModules:manifest.added,totalModules:220,moduleManifestSha:sha(fs.readFileSync(path.join(stage,'stream-stage-manifest.json'))),assetCount:Object.keys(assets).length,assetBytes:Object.values(assets).reduce((n,a)=>n+a.size,0),assets};
 report.planSha=sha(JSON.stringify(report));return {report,manifest};
}
/** 从Wrangler已有认证读取OAuth；只向固定官方API发出，不写文件、不打印。 */
function token(){if(oauth)return oauth;const candidates=[path.join(process.env.APPDATA,'xdg.config/.wrangler/config/default.toml'),path.join(process.env.USERPROFILE,'.wrangler/config/default.toml')];const file=candidates.find(f=>fs.existsSync(f));requireValue(file,'缺少Wrangler认证');oauth=fs.readFileSync(file,'utf8').match(/^oauth_token\s*=\s*"([^"]+)"/m)?.[1];requireValue(oauth,'无法识别认证配置');return oauth;}
/** 固定目标API，不重试版本创建或切流，错误不包含请求头和响应全文。 */
async function api(suffix,{method='GET',body,uploadToken}={}){const response=await fetch(apiRoot+suffix,{method,headers:{Authorization:'Bearer '+(uploadToken||token()),...(body&&!(body instanceof FormData)?{'Content-Type':'application/json'}:{})},body:body instanceof FormData?body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(180000)});const data=await response.json();if(!response.ok||!data.success)throw new Error(`Cloudflare ${method} ${suffix.split('?')[0]} HTTP ${response.status}: `+(data.errors||[]).map(e=>`${e.code}: ${e.message}`).join(';').slice(0,500));return data.result;}
/** 确认当前100%部署仍是预期，其他人的新发布绝不覆盖。 */
async function deploymentGuard(expected){const result=await api(scriptPath+'/deployments');const list=Array.isArray(result)?result:result.deployments;requireValue(Array.isArray(list)&&list.length,'无法核对当前部署');const latest=[...list].sort((a,b)=>Date.parse(b.created_on)-Date.parse(a.created_on))[0];requireValue(latest.versions.length===1&&latest.versions[0].version_id===expected&&latest.versions[0].percentage===100,'当前部署已变，停止以避免覆盖他人成果');return latest;}
/** 仅上传候选版本；所有原绑定沿用，secret使用严格继承，绝不获取明文。 */
async function upload(report,manifest){
 requireValue(!fs.existsSync(receiptPath),'已有上传回执，请先检查，禁止盲目重复创建版本');await deploymentGuard(original);
 const versions=await api(scriptPath+'/versions');const items=Array.isArray(versions)?versions:versions.items;requireValue(items?.[0]?.id===original,'最新上传版本发生变化，不能盲目继承secret');
 const baseline=read(path.join(snapshot,'settings.bin')).result;const current=await api(scriptPath+'/settings');requireValue(JSON.stringify(current.bindings)===JSON.stringify(baseline.bindings),'线上绑定已变');requireValue(current.compatibility_date===baseline.compatibility_date&&JSON.stringify(current.compatibility_flags)===JSON.stringify(baseline.compatibility_flags),'运行时配置已变');
 const assetManifest=Object.fromEntries(Object.entries(report.assets).map(([name,a])=>[name,{hash:a.hash,size:a.size}]));const session=await api(scriptPath+'/assets-upload-session',{method:'POST',body:{manifest:assetManifest}});let completion=session.buckets.length?null:session.jwt;
 const byHash=new Map(Object.entries(report.assets).map(([name,a])=>[a.hash,{name,...a}]));
 for(const bucket of session.buckets){const form=new FormData();for(const hash of bucket){const a=byHash.get(hash);requireValue(a,'平台请求未知资产摘要');form.append(hash,new Blob([fs.readFileSync(path.join(dist,a.name.slice(1))).toString('base64')],{type:a.type}),hash);}const result=await api('/workers/assets/upload?base64=true',{method:'POST',body:form,uploadToken:session.jwt});if(result?.jwt)completion=result.jwt;}
 requireValue(completion,'没有静态资源完成凭证');requireValue(plan().report.planSha===report.planSha,'上传期间发布文件漂移');await deploymentGuard(original);
 const bindings=baseline.bindings.map(binding=>binding.type==='secret_text'?{name:binding.name,type:'inherit'}:binding.type==='d1'?{name:binding.name,type:'d1',id:binding.id||binding.database_id}:binding);
 const metadata={main_module:'worker.py',bindings,compatibility_date:baseline.compatibility_date,compatibility_flags:baseline.compatibility_flags,usage_model:baseline.usage_model,observability:baseline.observability,assets:{jwt:completion,config:{not_found_handling:'single-page-application',run_worker_first:['/api','/api/*','/media','/media/*']}},annotations:{'workers/message':'Vue trial + web pet drag + true SSE; preserve live AI 5e7bd074 (no data migration)'}};
 const form=new FormData();form.append('metadata',JSON.stringify(metadata));for(const module of manifest.modules)form.append(module.name,new Blob([fs.readFileSync(path.join(stage,'modules',module.name))],{type:module.type}),module.name);
 const version=await api(scriptPath+'/versions?bindings_inherit=strict',{method:'POST',body:form});requireValue(version.id,'创建版本未返回ID');const receipt={versionId:version.id,original,planSha:report.planSha,uploadedAt:new Date().toISOString(),previewUrl:`https://${version.id.slice(0,8)}-zhuanjiao.wangzirui471.workers.dev`,bindings:bindings.map(b=>({name:b.name,type:b.type})),handlers:version.resources?.script?.handlers};fs.writeFileSync(receiptPath,JSON.stringify(receipt,null,2));console.log(JSON.stringify(receipt));
}
/** 切100%流量或回退，不更改Cron、资源和数据库；必须先有候选验证记录。 */
async function deploy(mode,report){const receipt=read(receiptPath);requireValue(receipt.original===original&&receipt.planSha===report.planSha,'上传与待发布候选不一致');if(mode==='activate'){const smoke=read(path.join(stage,'preview-smoke.json'));requireValue(smoke.ok===true&&smoke.versionId===receipt.versionId,'缺少当前候选线上只读预览验收');}const target=mode==='activate'?receipt.versionId:original;await deploymentGuard(mode==='activate'?original:receipt.versionId);const result=await api(scriptPath+'/deployments',{method:'POST',body:{strategy:'percentage',versions:[{version_id:target,percentage:100}],annotations:{'workers/message':mode==='activate'?'Publish verified Vue pet and streaming slice':'Rollback pet release to original preserved AI'}}});fs.writeFileSync(path.join(stage,mode+'-receipt.json'),JSON.stringify({id:result.id,target,at:new Date().toISOString(),original},null,2));console.log(JSON.stringify({mode,deploymentId:result.id,versionId:target}));}
/** 默认只生成可审阅清单；显式模式才操作用户已授权的原Worker。 */
async function main(){const mode=process.argv[2]||'plan';requireValue(['plan','upload','activate','rollback'].includes(mode),'未知模式');const {report,manifest}=plan();if(mode==='plan'){fs.writeFileSync(path.join(stage,'release-plan.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({...report,assets:undefined}));}else if(mode==='upload')await upload(report,manifest);else await deploy(mode,report);}
main().catch(error=>{console.error(error.message);process.exit(1)});
