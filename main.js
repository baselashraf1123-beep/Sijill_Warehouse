const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const { autoUpdater } = require('electron-updater');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');

let win;
let updateConfigured = false;
let updateState = { status: 'idle', version: app.getVersion(), message: 'التحديثات غير مهيأة بعد' };
const root = () => path.join(app.getPath('userData'), 'archive_vault');
const dbFile = () => path.join(root(), 'sijill-data.json');
function ensure(){ const r=root(); for(const d of ['vault','thumbs','exports']) fs.mkdirSync(path.join(r,d),{recursive:true}); if(!fs.existsSync(dbFile())) fs.writeFileSync(dbFile(), JSON.stringify({version:1,documents:[],folders:[],audit:[]},null,2)); }
function load(){ ensure(); return JSON.parse(fs.readFileSync(dbFile(),'utf8')); }
function save(db){ fs.writeFileSync(dbFile(), JSON.stringify(db,null,2)); }
function hash(file){ return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'); }
function uid(prefix){return prefix+'_'+crypto.randomBytes(7).toString('hex');}
function log(db,action,docId,details){db.audit.push({action,docId,details,createdAt:new Date().toISOString()});}
function emitUpdate(state){ updateState={...updateState,...state}; if(win && !win.isDestroyed()) win.webContents.send('update-status', updateState); }
function configureUpdates(){
  // Set SIJILL_UPDATE_URL or place update-config.json in the userData folder.
  let updateUrl=process.env.SIJILL_UPDATE_URL || '';
  try { const cfg=path.join(app.getPath('userData'),'update-config.json'); if(fs.existsSync(cfg)) updateUrl=JSON.parse(fs.readFileSync(cfg,'utf8')).updateUrl || updateUrl; } catch {}
  if(!updateUrl){ emitUpdate({status:'unconfigured',message:'سيتم تفعيل التحديثات عند ربط خادم الإصدارات'}); return; }
  try {
    autoUpdater.autoDownload=false; autoUpdater.autoInstallOnAppQuit=true;
    autoUpdater.setFeedURL({provider:'generic',url:updateUrl.replace(/\/$/,'')+'/' });
    updateConfigured=true;
    autoUpdater.on('checking-for-update',()=>emitUpdate({status:'checking',message:'جارٍ التحقق من وجود تحديثات...'}));
    autoUpdater.on('update-available',info=>emitUpdate({status:'available',version:info.version,message:`يتوفر إصدار جديد ${info.version}`}));
    autoUpdater.on('update-not-available',()=>emitUpdate({status:'current',message:'أنت تستخدم أحدث إصدار'}));
    autoUpdater.on('download-progress',p=>emitUpdate({status:'downloading',percent:Math.round(p.percent),message:`جارٍ تنزيل التحديث ${Math.round(p.percent)}%`}));
    autoUpdater.on('update-downloaded',info=>emitUpdate({status:'downloaded',version:info.version,message:'اكتمل تنزيل التحديث؛ سيُثبت عند إغلاق التطبيق'}));
    autoUpdater.on('error',err=>emitUpdate({status:'error',message:`تعذر التحقق من التحديث: ${err.message}`}));
  } catch(err){ emitUpdate({status:'error',message:`تعذر تهيئة التحديث: ${err.message}`}); }
}
function createWindow(){ win=new BrowserWindow({width:1440,height:920,minWidth:1120,minHeight:720,backgroundColor:'#f5f7fb',webPreferences:{preload:path.join(__dirname,'preload.js'),contextIsolation:true,nodeIntegration:false}}); win.loadFile('index.html'); win.webContents.once('did-finish-load',()=>{win.webContents.send('update-status',updateState); if(updateConfigured) setTimeout(()=>autoUpdater.checkForUpdates().catch(()=>{}),2500);}); }
app.whenReady().then(()=>{ensure();configureUpdates();createWindow();app.on('activate',()=>{if(BrowserWindow.getAllWindows().length===0)createWindow()})}); app.on('window-all-closed',()=>{if(process.platform!=='darwin')app.quit()});

ipcMain.handle('state',()=>{const db=load(); return {root:root(),documents:db.documents,folders:db.folders,stats:{total_docs:db.documents.length,total_folders:db.folders.length,pending_review:db.documents.filter(x=>x.auditStatus==='قيد المراجعة').length,expiring_30_days:db.documents.filter(x=>x.expiryDate && (new Date(x.expiryDate)-new Date())<=30*86400000).length,total_size_bytes:db.documents.reduce((a,x)=>a+(x.fileSize||0),0)}}});
ipcMain.handle('update-status',()=>updateState);
ipcMain.handle('check-updates',async()=>{if(!updateConfigured){emitUpdate({status:'unconfigured',message:'خادم التحديث غير مهيأ لهذه النسخة'});return updateState;} try{await autoUpdater.checkForUpdates();}catch(err){emitUpdate({status:'error',message:`تعذر التحقق من التحديث: ${err.message}`});} return updateState;});
ipcMain.handle('download-update',async()=>{if(updateConfigured) await autoUpdater.downloadUpdate(); return updateState;});
ipcMain.handle('install-update',()=>{if(updateConfigured && updateState.status==='downloaded') autoUpdater.quitAndInstall(false,true);});
ipcMain.handle('choose-image',async()=>{const r=await dialog.showOpenDialog(win,{title:'اختيار صورة المستند',properties:['openFile'],filters:[{name:'صور المستندات',extensions:['png','jpg','jpeg','webp','bmp','tif','tiff']}]});return r.canceled?null:r.filePaths[0]});
ipcMain.handle('add',(_,data)=>{const db=load();const src=data.source; if(!src||!fs.existsSync(src))throw Error('الملف غير موجود'); const ext=path.extname(src).toLowerCase(); if(!['.png','.jpg','.jpeg','.webp','.bmp','.tif','.tiff'].includes(ext))throw Error('صيغة الصورة غير مدعومة'); const sha=hash(src); const dup=db.documents.find(x=>x.sha256===sha); if(dup)throw Error(`هذا المستند مكرر بالفعل: ${dup.title}`); const id=uid('doc'); const date=data.docDate||new Date().toISOString().slice(0,10); const wh=(data.warehouse||'المخزن الرئيسي').replaceAll('/','-'); const dir=path.join(root(),'vault',wh,date.slice(0,7)); fs.mkdirSync(dir,{recursive:true}); const dest=path.join(dir,id+ext); fs.copyFileSync(src,dest); const stat=fs.statSync(dest); const doc={id,title:data.title||path.basename(src),folderId:data.folderId||null,docType:data.docType||'إذن إضافة',refNumber:data.refNumber||'',poNumber:data.poNumber||'',warehouse:data.warehouse||'المخزن الرئيسي',issuer:data.issuer||'',keeper:data.keeper||'',batchNumber:data.batchNumber||'',auditStatus:data.auditStatus||'قيد المراجعة',docDate:date,expiryDate:data.expiryDate||'',ocrText:data.ocrText||'',notes:data.notes||'',fileName:path.basename(src),filePath:path.relative(root(),dest),sha256:sha,fileSize:stat.size,isStarred:0,tags:(data.tags||'').split(',').map(x=>x.trim()).filter(Boolean),createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()}; db.documents.unshift(doc); log(db,'ADD_DOCUMENT',id,`أرشفة: ${doc.title}`);save(db);return doc});
ipcMain.handle('delete',(_,id)=>{const db=load();const i=db.documents.findIndex(x=>x.id===id);if(i<0)return;const d=db.documents[i];try{fs.unlinkSync(path.join(root(),d.filePath))}catch{};db.documents.splice(i,1);log(db,'DELETE_DOCUMENT',id,`حذف: ${d.title}`);save(db)});
ipcMain.handle('update',(_,data)=>{const db=load();const d=db.documents.find(x=>x.id===data.id);if(!d)throw Error('المستند غير موجود');Object.assign(d,data,{updatedAt:new Date().toISOString()});log(db,'UPDATE_DOCUMENT',d.id,`تحديث: ${d.title}`);save(db);return d});
ipcMain.handle('folder',(_,name)=>{const db=load();const f={id:uid('fld'),name:name.trim(),createdAt:new Date().toISOString()};db.folders.push(f);log(db,'CREATE_FOLDER',null,`إنشاء خزانة: ${f.name}`);save(db);return f});
ipcMain.handle('export-csv',async()=>{const r=await dialog.showSaveDialog(win,{defaultPath:path.join(root(),'exports','warehouse_register.csv')});if(r.canceled)return;const db=load();const head=['المعرف','العنوان','النوع','الرقم المرجعي','أمر الشراء PO','المخزن','المورد/الجهة','أمين المخزن','رقم التشغيلة','حالة الاعتماد','تاريخ المستند','تاريخ الانتهاء','الوسوم'];const esc=x=>'"'+String(x??'').replaceAll('"','""')+'"';const rows=[head,...db.documents.map(d=>[d.id,d.title,d.docType,d.refNumber,d.poNumber,d.warehouse,d.issuer,d.keeper,d.batchNumber,d.auditStatus,d.docDate,d.expiryDate,d.tags.join(', ')])].map(x=>x.map(esc).join(','));fs.writeFileSync(r.filePath,'\ufeff'+rows.join('\n'),'utf8');return r.filePath});
ipcMain.handle('backup',async()=>{const r=await dialog.showSaveDialog(win,{defaultPath:path.join(root(),'exports','sijill-backup.json')});if(r.canceled)return;fs.copyFileSync(dbFile(),r.filePath);return r.filePath});
ipcMain.handle('open-file',(_,rel)=>shell.openPath(path.join(root(),rel)));
