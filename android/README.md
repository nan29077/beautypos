# BeautyPOS Android app

This Android WebView client connects to the existing FastAPI BeautyPOS server.

## Build

1. Install JDK 17 and Android SDK Platform 35.
2. Set `JAVA_HOME` and create `local.properties` with `sdk.dir=...`.
3. Run `gradlew.bat assembleDebug` in this directory.
4. Install `app/build/outputs/apk/debug/app-debug.apk`.

The app opens the production server at `https://ad-pay.co.kr` by default. Use the
app menu's server-address item only when connecting to a development server. For
a physical phone on the same Wi-Fi as the development PC, use
`http://<PC IPv4 address>:3000`; an Android emulator can use
`http://10.0.2.2:3000` to reach the host PC.

For production, deploy the FastAPI service behind HTTPS and enter its `https://`
URL. A Play Store/release build additionally requires a private signing key.
