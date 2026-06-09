Place the app icons here before running `npm run dist:mac` / `dist:win`:

  icon.icns   macOS app icon  (1024x1024 source recommended)
  icon.ico    Windows app icon (256x256)

electron-builder reads these paths from electron-builder.yml (mac.icon / win.icon).
Until they exist, electron-builder uses its default Electron icon (and may warn).
