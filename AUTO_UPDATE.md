# التحديث التلقائي عبر GitHub Releases

التطبيق مضبوط الآن على مستودع GitHub العام:

```text
https://github.com/baselashraf1123-beep/Sijill_Warehouse
```

يستخدم التطبيق `electron-updater` مع GitHub Provider. عند تشغيل نسخة مثبتة، يفحص أحدث GitHub Release، ويعرض زر تنزيل عند توفر إصدار أحدث، ثم يثبت التحديث عند إعادة التشغيل.

## نشر إصدار جديد

1. ارفع رقم `version` في `package.json`، مثلاً من `1.0.0` إلى `1.0.1`.
2. أنشئ GitHub token بصلاحية إنشاء ورفع Releases وضعه في متغير البيئة `GH_TOKEN` فقط.
3. نفّذ:

```bash
npm install
npm run release:win
```

أو:

```bash
npx electron-builder --win nsis --publish always
```

ينتج البناء ويرفع الملفات اللازمة، ومنها:

- `latest.yml`
- ملف Installer بصيغة `.exe`
- ملف `.blockmap`

يجب أن يكون الإصدار الجديد أعلى من الإصدار المثبت وأن يكون GitHub Release منشوراً، وليس Draft أو Pre-release غير مقصود.

## الاختبار

ثبّت النسخة القديمة، ثم انشر نسخة أعلى، وافتح التطبيق القديم واضغط زر «التحديثات». يجب أن يظهر الإصدار الجديد، ثم يمكن تنزيله وإعادة تشغيل التطبيق لتثبيته.

لا تضع `GH_TOKEN` داخل `package.json` أو داخل ملفات التطبيق.
