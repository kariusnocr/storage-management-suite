package io.github.kariusnocr.kas;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.JavascriptInterface;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;

public class MainActivity extends Activity {
    private static final String PREFS_NAME = "kas_android_prefs";
    private static final String KEY_SERVER_MODE = "server_mode";
    private static final String KEY_REMOTE_URL = "remote_url";
    private static final int FILE_CHOOSER_REQ_CODE = 1001;
    private static final int STORAGE_PERM_REQ_CODE = 1002;

    private WebView webView;
    private LinearLayout bootOverlay;
    private TextView bootStatusText;
    private ValueCallback<Uri[]> filePathCallback;
    private volatile String localServerUrl = "http://127.0.0.1:8765";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        configureSystemBars();

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.parseColor("#0B0F17"));

        webView = new WebView(this);
        webView.setBackgroundColor(Color.parseColor("#0B0F17"));
        configureWebView(webView);
        root.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        ));

        bootOverlay = createBootOverlay();
        root.addView(bootOverlay, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        ));

        setContentView(root);
        startEmbeddedKasEngineAsync();
    }

    private void configureSystemBars() {
        try {
            Window window = getWindow();
            if (window != null) {
                window.setStatusBarColor(Color.parseColor("#0B0F17"));
                window.setNavigationBarColor(Color.parseColor("#0B0F17"));
            }
        } catch (Exception ignored) {
        }
    }

    private LinearLayout createBootOverlay() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setBackgroundColor(Color.parseColor("#0B0F17"));
        box.setPadding(64, 64, 64, 64);

        ProgressBar spinner = new ProgressBar(this);
        box.addView(spinner, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));

        TextView title = new TextView(this);
        title.setText("Karius Academic System (KAS) v1.7.0");
        title.setTextColor(Color.parseColor("#F1F5F9"));
        title.setTextSize(17f);
        title.setGravity(Gravity.CENTER);
        title.setPadding(0, 36, 0, 12);
        box.addView(title);

        bootStatusText = new TextView(this);
        bootStatusText.setText("Đang khởi chạy máy chủ Python 3.11 & SQLite nội bộ trên Android...");
        bootStatusText.setTextColor(Color.parseColor("#94A3B8"));
        bootStatusText.setTextSize(13.5f);
        bootStatusText.setGravity(Gravity.CENTER);
        box.addView(bootStatusText);

        return box;
    }

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    private void configureWebView(WebView wv) {
        WebSettings ws = wv.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setDatabaseEnabled(true);
        ws.setAllowFileAccess(true);
        ws.setAllowContentAccess(true);
        ws.setLoadsImagesAutomatically(true);
        ws.setMediaPlaybackRequiresUserGesture(false);
        ws.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        ws.setUserAgentString(ws.getUserAgentString() + " KASAndroid/1.7.0");

        CookieManager cm = CookieManager.getInstance();
        cm.setAcceptCookie(true);
        cm.setAcceptThirdPartyCookies(wv, true);

        wv.addJavascriptInterface(new KasJsBridge(), "KASAndroid");

        wv.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (uri == null) return false;
                String host = uri.getHost() != null ? uri.getHost().toLowerCase() : "";
                if (host.contains("accounts.google.com")
                        || host.contains("drive.google.com")
                        || host.contains("github.com")) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, uri));
                        return true;
                    } catch (Exception ignored) {
                    }
                }
                return false;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                if (bootOverlay != null && bootOverlay.getVisibility() == View.VISIBLE) {
                    bootOverlay.setVisibility(View.GONE);
                }
            }
        });

        wv.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(
                    WebView webView,
                    ValueCallback<Uri[]> filePathCallback,
                    FileChooserParams fileChooserParams
            ) {
                if (MainActivity.this.filePathCallback != null) {
                    MainActivity.this.filePathCallback.onReceiveValue(null);
                }
                MainActivity.this.filePathCallback = filePathCallback;
                try {
                    Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
                    intent.addCategory(Intent.CATEGORY_OPENABLE);
                    intent.setType("*/*");
                    startActivityForResult(Intent.createChooser(intent, "Chọn tệp cho KAS"), FILE_CHOOSER_REQ_CODE);
                    return true;
                } catch (Exception e) {
                    MainActivity.this.filePathCallback = null;
                    return false;
                }
            }
        });

        wv.setDownloadListener(new DownloadListener() {
            @Override
            public void onDownloadStart(String url, String userAgent, String contentDisposition, String mimeType, long contentLength) {
                try {
                    DownloadManager.Request req = new DownloadManager.Request(Uri.parse(url));
                    String fileName = URLUtil.guessFileName(url, contentDisposition, mimeType);
                    req.setMimeType(mimeType);
                    req.addRequestHeader("User-Agent", userAgent);
                    req.setTitle(fileName);
                    req.setDescription("Tải tệp từ Karius Academic System (KAS)");
                    req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                    req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName);
                    DownloadManager dm = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
                    if (dm != null) {
                        dm.enqueue(req);
                        Toast.makeText(MainActivity.this, "Đang tải về Downloads: " + fileName, Toast.LENGTH_SHORT).show();
                    }
                } catch (Exception e) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                    } catch (Exception ignored) {
                    }
                }
            }
        });
    }

    private void startEmbeddedKasEngineAsync() {
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    if (!Python.isStarted()) {
                        Python.start(new AndroidPlatform(getApplicationContext()));
                    }
                    Python py = Python.getInstance();
                    PyObject bootMod = py.getModule("kas_android_boot");
                    String filesDir = getFilesDir().getAbsolutePath();
                    File extFile = getExternalFilesDir(null);
                    String extDir = (extFile != null) ? extFile.getAbsolutePath() : filesDir;
                    PyObject urlObj = bootMod.callAttr("start_server_url", filesDir, extDir, 8765);
                    if (urlObj != null) {
                        localServerUrl = urlObj.toString();
                    }
                } catch (final Exception e) {
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            if (bootStatusText != null) {
                                bootStatusText.setText("Lỗi khởi chạy nội bộ: " + e.getMessage());
                            }
                        }
                    });
                }

                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        webView.loadUrl(getEffectiveTargetUrl());
                    }
                });
            }
        }, "kas-android-boot").start();
    }

    private String getEffectiveTargetUrl() {
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        String mode = prefs.getString(KEY_SERVER_MODE, "local");
        String remote = prefs.getString(KEY_REMOTE_URL, "");
        if ("remote".equals(mode) && remote != null && !remote.trim().isEmpty()) {
            return remote.trim();
        }
        return localServerUrl;
    }

    public void showServerSwitcherDialog() {
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        String currentRemote = prefs.getString(KEY_REMOTE_URL, "http://192.168.1.10:8765");

        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(48, 32, 48, 16);

        TextView hint = new TextView(this);
        hint.setText("Nhập địa chỉ LAN của máy chủ KAS trên máy tính (hoặc bấm 'Dùng Máy Chủ Nội Bộ' để chạy độc lập 100% trên điện thoại Android):");
        hint.setTextSize(13f);
        layout.addView(hint);

        final EditText input = new EditText(this);
        input.setText(currentRemote);
        input.setHint("http://192.168.1.x:8765");
        input.setSingleLine(true);
        layout.addView(input);

        new AlertDialog.Builder(this)
                .setTitle("Chế độ Máy chủ KAS trên Android")
                .setView(layout)
                .setPositiveButton("Kết nối PC qua Wi-Fi", (dialog, which) -> {
                    String raw = input.getText().toString().trim();
                    if (!raw.isEmpty()) {
                        if (!raw.startsWith("http://") && !raw.startsWith("https://")) {
                            raw = "http://" + raw;
                        }
                        prefs.edit()
                                .putString(KEY_SERVER_MODE, "remote")
                                .putString(KEY_REMOTE_URL, raw)
                                .apply();
                        webView.loadUrl(raw);
                        Toast.makeText(MainActivity.this, "Đã chuyển sang máy chủ LAN: " + raw, Toast.LENGTH_SHORT).show();
                    }
                })
                .setNeutralButton("Dùng Máy Chủ Nội Bộ (Android)", (dialog, which) -> {
                    prefs.edit().putString(KEY_SERVER_MODE, "local").apply();
                    webView.loadUrl(localServerUrl);
                    Toast.makeText(MainActivity.this, "Đang dùng máy chủ KAS nội bộ trên Android.", Toast.LENGTH_SHORT).show();
                })
                .setNegativeButton("Đóng", null)
                .show();
    }

    public void requestAndroidStoragePermissionFlow() {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                if (!Environment.isExternalStorageManager()) {
                    try {
                        Intent intent = new Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION);
                        intent.setData(Uri.parse("package:" + getPackageName()));
                        startActivity(intent);
                    } catch (Exception e) {
                        Intent intent = new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION);
                        startActivity(intent);
                    }
                } else {
                    Toast.makeText(this, "Ứng dụng đã có toàn quyền truy cập bộ nhớ Android.", Toast.LENGTH_SHORT).show();
                }
            } else {
                if (checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
                    requestPermissions(new String[]{
                            Manifest.permission.READ_EXTERNAL_STORAGE,
                            Manifest.permission.WRITE_EXTERNAL_STORAGE
                    }, STORAGE_PERM_REQ_CODE);
                } else {
                    Toast.makeText(this, "Ứng dụng đã có quyền đọc/ghi bộ nhớ Android.", Toast.LENGTH_SHORT).show();
                }
            }
        } catch (Exception e) {
            Toast.makeText(this, "Không thể mở màn hình cấp quyền: " + e.getMessage(), Toast.LENGTH_SHORT).show();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == FILE_CHOOSER_REQ_CODE) {
            if (filePathCallback == null) return;
            Uri[] results = null;
            if (resultCode == Activity.RESULT_OK && data != null) {
                String dataString = data.getDataString();
                if (dataString != null) {
                    results = new Uri[]{Uri.parse(dataString)};
                }
            }
            filePathCallback.onReceiveValue(results);
            filePathCallback = null;
        }
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (webView != null) {
            webView.evaluateJavascript(
                    "(function(){ return (window.kasHandleAndroidBack && window.kasHandleAndroidBack()) ? '1' : '0'; })()",
                    value -> {
                        if (value != null && value.contains("1")) {
                            return;
                        }
                        if (webView.canGoBack()) {
                            webView.goBack();
                        } else {
                            MainActivity.super.onBackPressed();
                        }
                    }
            );
            return;
        }
        super.onBackPressed();
    }

    public class KasJsBridge {
        @JavascriptInterface
        public String getVersion() {
            return "1.7.0";
        }

        @JavascriptInterface
        public String getServerMode() {
            SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
            return prefs.getString(KEY_SERVER_MODE, "local");
        }

        @JavascriptInterface
        public String getActiveServerUrl() {
            return getEffectiveTargetUrl();
        }

        @JavascriptInterface
        public void showServerSwitcher() {
            runOnUiThread(() -> showServerSwitcherDialog());
        }

        @JavascriptInterface
        public void requestStorageAccess() {
            runOnUiThread(() -> requestAndroidStoragePermissionFlow());
        }
    }
}
