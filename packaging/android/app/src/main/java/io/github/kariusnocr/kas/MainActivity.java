package io.github.kariusnocr.kas;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.content.pm.SigningInfo;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.DhcpInfo;
import android.net.Uri;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.Settings;
import android.view.Gravity;
import android.view.HapticFeedbackConstants;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowInsetsController;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.JavascriptInterface;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.TimeZone;

public class MainActivity extends Activity {
    private static final String KAS_VERSION = "1.9.0";
    private static final String PREFS_NAME = "kas_android_prefs";
    private static final String KEY_SERVER_MODE = "server_mode";
    private static final String KEY_REMOTE_URL = "remote_url";
    private static final String KEY_LAST_THEME = "last_theme";
    private static final int FILE_CHOOSER_REQ_CODE = 1001;
    private static final int STORAGE_PERM_REQ_CODE = 1002;
    private static final int LAN_DISCOVERY_PORT = 8766;
    private static final String LAN_DISCOVERY_PROBE = "KAS_DISCOVER_V1";
    private static final long MAX_NATIVE_LOG_BYTES = 512L * 1024L;

    private static final int COLOR_DARK_BG = Color.parseColor("#0C0E12");
    private static final int COLOR_DARK_NAV = Color.parseColor("#101319");
    private static final int COLOR_LIGHT_BG = Color.parseColor("#F6F5F1");
    private static final int COLOR_LIGHT_NAV = Color.parseColor("#FFFFFF");

    private FrameLayout rootContainer;
    private WebView webView;
    private LinearLayout bootOverlay;
    private TextView bootStatusText;
    private ValueCallback<Uri[]> filePathCallback;
    private volatile String localServerUrl = "http://127.0.0.1:8765";
    private volatile boolean userManuallyNavigated = false;
    private volatile String pendingApkInstallPath = null;
    private volatile boolean recoveryDialogShowing = false;

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        installUncaughtCrashLogger();
        appendNativeLog("INFO", "lifecycle", "Khoi dong KAS Android v" + KAS_VERSION + " (" + Build.MODEL + ", Android " + Build.VERSION.RELEASE + ")");

        rootContainer = new FrameLayout(this);
        rootContainer.setBackgroundColor(COLOR_DARK_BG);

        webView = new WebView(this);
        webView.setBackgroundColor(COLOR_DARK_BG);
        configureWebView(webView);
        rootContainer.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        ));

        bootOverlay = createBootOverlay();
        rootContainer.addView(bootOverlay, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        ));

        setContentView(rootContainer);
        applySystemBarsTheme(false);
        startEmbeddedKasEngineAsync();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (pendingApkInstallPath != null) {
            if (getPackageManager().canRequestPackageInstalls()) {
                String path = pendingApkInstallPath;
                pendingApkInstallPath = null;
                appendNativeLog("INFO", "updater", "Da cap quyen cai dat APK, tu dong mo trinh cai dat: " + path);
                installApkFile(path, "");
            }
        }
    }

    private File getNativeLogFile() {
        File dir = new File(getFilesDir(), "kas/data/logs");
        if (!dir.exists()) {
            dir.mkdirs();
        }
        return new File(dir, "android_native.log");
    }

    private synchronized void appendNativeLog(String level, String category, String message) {
        try {
            File logFile = getNativeLogFile();
            if (logFile.exists() && logFile.length() > MAX_NATIVE_LOG_BYTES) {
                File backup = new File(logFile.getParentFile(), "android_native.log.1");
                if (backup.exists()) {
                    backup.delete();
                }
                logFile.renameTo(backup);
            }
            SimpleDateFormat sdf = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US);
            sdf.setTimeZone(TimeZone.getTimeZone("UTC"));
            String ts = sdf.format(new Date());
            String cleanMsg = (message != null ? message : "").replace("\r", " ").replace("\n", " | ");
            String line = "[" + ts + "] [" + level + "] [" + category + "] " + cleanMsg + "\n";
            try (FileOutputStream fos = new FileOutputStream(logFile, true)) {
                fos.write(line.getBytes(StandardCharsets.UTF_8));
            }
        } catch (Exception ignored) {
        }
    }

    private String readNativeLogsText() {
        try {
            File logFile = getNativeLogFile();
            if (!logFile.isFile()) {
                return "";
            }
            byte[] raw = Files.readAllBytes(logFile.toPath());
            String text = new String(raw, StandardCharsets.UTF_8);
            if (text.length() > 60000) {
                return text.substring(text.length() - 60000);
            }
            return text;
        } catch (Exception e) {
            return "";
        }
    }

    private void installUncaughtCrashLogger() {
        final Thread.UncaughtExceptionHandler prev = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((thread, throwable) -> {
            try {
                StringWriter sw = new StringWriter();
                throwable.printStackTrace(new PrintWriter(sw));
                appendNativeLog("CRITICAL", "android_crash", "Thread " + thread.getName() + ": " + sw.toString());
            } catch (Exception ignored) {
            }
            if (prev != null) {
                prev.uncaughtException(thread, throwable);
            }
        });
    }

    private void applySystemBarsTheme(boolean isLight) {
        try {
            int statusColor = isLight ? COLOR_LIGHT_BG : COLOR_DARK_BG;
            int navColor = isLight ? COLOR_LIGHT_NAV : COLOR_DARK_NAV;

            if (rootContainer != null) {
                rootContainer.setBackgroundColor(statusColor);
            }
            if (webView != null) {
                webView.setBackgroundColor(statusColor);
            }

            Window window = getWindow();
            if (window == null) {
                return;
            }
            window.setStatusBarColor(statusColor);
            window.setNavigationBarColor(navColor);

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                WindowInsetsController controller = window.getInsetsController();
                if (controller != null) {
                    int lightMask = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                            | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                    controller.setSystemBarsAppearance(isLight ? lightMask : 0, lightMask);
                }
            } else {
                applyLegacySystemBarsAppearance(window, isLight);
            }

            getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
                    .edit()
                    .putString(KEY_LAST_THEME, isLight ? "light" : "dark")
                    .apply();
        } catch (Exception ignored) {
        }
    }

    @SuppressWarnings("deprecation")
    private void applyLegacySystemBarsAppearance(Window window, boolean isLight) {
        View decor = window.getDecorView();
        if (decor == null) {
            return;
        }
        int flags = decor.getSystemUiVisibility();
        if (isLight) {
            flags |= View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
        } else {
            flags &= ~(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        }
        decor.setSystemUiVisibility(flags);
    }

    private void hideBootOverlaySmoothly() {
        if (bootOverlay != null && bootOverlay.getVisibility() == View.VISIBLE) {
            bootOverlay.animate()
                    .alpha(0f)
                    .setDuration(220)
                    .withEndAction(() -> bootOverlay.setVisibility(View.GONE))
                    .start();
        }
    }

    private LinearLayout createBootOverlay() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setBackgroundColor(COLOR_DARK_BG);
        box.setPadding(dp(28), dp(36), dp(28), dp(36));

        GradientDrawable badgeBg = new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{Color.parseColor("#2F81F7"), Color.parseColor("#58A6FF")}
        );
        badgeBg.setCornerRadius(dp(18));

        TextView brandBadge = new TextView(this);
        brandBadge.setText("KAS");
        brandBadge.setTextColor(Color.WHITE);
        brandBadge.setTextSize(22f);
        brandBadge.setTypeface(Typeface.DEFAULT_BOLD);
        brandBadge.setGravity(Gravity.CENTER);
        brandBadge.setBackground(badgeBg);
        LinearLayout.LayoutParams badgeLp = new LinearLayout.LayoutParams(dp(72), dp(72));
        badgeLp.bottomMargin = dp(20);
        box.addView(brandBadge, badgeLp);

        TextView title = new TextView(this);
        title.setText("KAS");
        title.setTextColor(Color.parseColor("#EEF2F6"));
        title.setTextSize(22f);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setGravity(Gravity.CENTER);
        box.addView(title);

        TextView versionSub = new TextView(this);
        versionSub.setText("Karius Academic System · v" + KAS_VERSION);
        versionSub.setTextColor(Color.parseColor("#58A6FF"));
        versionSub.setTextSize(12.5f);
        versionSub.setTypeface(Typeface.DEFAULT_BOLD);
        versionSub.setGravity(Gravity.CENTER);
        versionSub.setPadding(0, dp(4), 0, dp(24));
        box.addView(versionSub);

        ProgressBar spinner = new ProgressBar(this);
        spinner.setIndeterminateTintList(ColorStateList.valueOf(Color.parseColor("#2F81F7")));
        LinearLayout.LayoutParams spinLp = new LinearLayout.LayoutParams(dp(36), dp(36));
        spinLp.bottomMargin = dp(16);
        box.addView(spinner, spinLp);

        bootStatusText = new TextView(this);
        bootStatusText.setText("Đang khởi chạy máy chủ Python 3.11 & SQLite nội bộ...");
        bootStatusText.setTextColor(Color.parseColor("#9AA4B2"));
        bootStatusText.setTextSize(13.5f);
        bootStatusText.setGravity(Gravity.CENTER);
        bootStatusText.setPadding(dp(8), 0, dp(8), dp(26));
        box.addView(bootStatusText);

        GradientDrawable btnBg = new GradientDrawable();
        btnBg.setColor(Color.parseColor("#171C24"));
        btnBg.setCornerRadius(dp(999));
        btnBg.setStroke(dp(1), Color.parseColor("#2E3746"));

        Button lanBtn = new Button(this);
        lanBtn.setText("Kết nối PC qua Wi-Fi");
        lanBtn.setAllCaps(false);
        lanBtn.setTextColor(Color.parseColor("#EEF2F6"));
        lanBtn.setTextSize(13.5f);
        lanBtn.setBackground(btnBg);
        lanBtn.setPadding(dp(20), dp(10), dp(20), dp(10));
        lanBtn.setMinHeight(dp(44));
        lanBtn.setOnClickListener(v -> showServerSwitcherDialog());
        box.addView(lanBtn, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));

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
        ws.setUserAgentString(ws.getUserAgentString() + " KASAndroid/" + KAS_VERSION);

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
                hideBootOverlaySmoothly();
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                if (request == null || !request.isForMainFrame()) {
                    return;
                }
                String failedUrl = request.getUrl() != null ? request.getUrl().toString() : "";
                int code = error != null ? error.getErrorCode() : -1;
                String desc = (error != null && error.getDescription() != null)
                        ? error.getDescription().toString()
                        : "Lỗi kết nối mạng";
                appendNativeLog("ERROR", "webview_network", "Loi tai trang (" + code + "): " + desc + " | URL=" + failedUrl);
                hideBootOverlaySmoothly();

                boolean isLocal = failedUrl.startsWith("http://127.0.0.1") || failedUrl.startsWith("http://localhost");
                if (!isLocal && !failedUrl.isEmpty()) {
                    runOnUiThread(() -> showRemoteRecoveryDialog(failedUrl, desc));
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
                    appendNativeLog("ERROR", "file_chooser", "Loi mo chon tep: " + e.getMessage());
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
                    req.setDescription("Tải tệp từ KAS");
                    req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                    req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName);
                    DownloadManager dm = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
                    if (dm != null) {
                        dm.enqueue(req);
                        Toast.makeText(MainActivity.this, "Đang tải về Downloads: " + fileName, Toast.LENGTH_SHORT).show();
                    }
                } catch (Exception e) {
                    appendNativeLog("WARNING", "download", "DownloadManager fallback: " + e.getMessage());
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                    } catch (Exception ignored) {
                    }
                }
            }
        });
    }

    private void showRemoteRecoveryDialog(String failedUrl, String errorDesc) {
        if (recoveryDialogShowing || isFinishing()) {
            return;
        }
        recoveryDialogShowing = true;
        new AlertDialog.Builder(this)
                .setTitle("Không kết nối được Máy chủ PC qua Wi-Fi")
                .setMessage(
                        "Không thể truy cập: " + failedUrl + "\n"
                                + "Chi tiết lỗi: " + errorDesc + "\n\n"
                                + "Kiểm tra nhanh trên PC:\n"
                                + "1. Mở KAS trên PC → Kho Dữ Liệu → bấm 'Bật Chia Sẻ Wi-Fi LAN' (hoặc chạy: kas android serve --port 8765).\n"
                                + "2. Đảm bảo điện thoại và PC dùng chung mạng Wi-Fi.\n"
                                + "3. Cho phép cổng TCP 8765 trong Windows Firewall (Private)."
                )
                .setCancelable(false)
                .setPositiveButton("Quay về Máy chủ Nội bộ (Android)", (d, w) -> {
                    recoveryDialogShowing = false;
                    SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
                    prefs.edit().putString(KEY_SERVER_MODE, "local").apply();
                    userManuallyNavigated = true;
                    webView.loadUrl(localServerUrl);
                })
                .setNeutralButton("Đổi địa chỉ / Tự tìm PC", (d, w) -> {
                    recoveryDialogShowing = false;
                    showServerSwitcherDialog();
                })
                .setNegativeButton("Thử lại", (d, w) -> {
                    recoveryDialogShowing = false;
                    webView.loadUrl(failedUrl);
                })
                .show();
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
                    appendNativeLog("INFO", "boot", "May chu Python noi bo san sang tai: " + localServerUrl);
                } catch (final Exception e) {
                    appendNativeLog("ERROR", "boot", "Loi khoi chay Chaquopy Python: " + e.getMessage());
                    runOnUiThread(() -> {
                        if (bootStatusText != null) {
                            bootStatusText.setText("Lỗi khởi chạy nội bộ: " + e.getMessage());
                        }
                    });
                }

                runOnUiThread(() -> {
                    if (!userManuallyNavigated) {
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

    private String normalizeServerUrl(String rawInput) {
        String s = rawInput == null ? "" : rawInput.trim();
        if (s.isEmpty()) {
            return "";
        }
        if (!s.startsWith("http://") && !s.startsWith("https://")) {
            s = "http://" + s;
        }
        while (s.endsWith("/")) {
            s = s.substring(0, s.length() - 1);
        }
        try {
            Uri u = Uri.parse(s);
            if (u.getHost() != null && u.getPort() == -1 && "http".equalsIgnoreCase(u.getScheme())) {
                s = "http://" + u.getHost() + ":8765" + (u.getPath() != null ? u.getPath() : "");
            }
        } catch (Exception ignored) {
        }
        return s;
    }

    private InetAddress computeWifiBroadcastAddress() {
        try {
            WifiManager wm = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            if (wm == null) return null;
            DhcpInfo dhcp = wm.getDhcpInfo();
            if (dhcp == null || dhcp.ipAddress == 0) return null;
            int broadcast = (dhcp.ipAddress & dhcp.netmask) | ~dhcp.netmask;
            byte[] quads = new byte[4];
            for (int k = 0; k < 4; k++) {
                quads[k] = (byte) ((broadcast >> (k * 8)) & 0xFF);
            }
            return InetAddress.getByAddress(quads);
        } catch (Exception e) {
            return null;
        }
    }

    private List<String> discoverLanPcServersBlocking() {
        Set<String> found = new LinkedHashSet<>();
        DatagramSocket sock = null;
        try {
            sock = new DatagramSocket();
            sock.setBroadcast(true);
            sock.setSoTimeout(450);

            byte[] probe = LAN_DISCOVERY_PROBE.getBytes(StandardCharsets.UTF_8);
            List<InetAddress> targets = new ArrayList<>();
            targets.add(InetAddress.getByName("255.255.255.255"));
            InetAddress subnetBcast = computeWifiBroadcastAddress();
            if (subnetBcast != null) {
                targets.add(subnetBcast);
            }
            for (InetAddress target : targets) {
                try {
                    DatagramPacket pkt = new DatagramPacket(probe, probe.length, target, LAN_DISCOVERY_PORT);
                    sock.send(pkt);
                } catch (Exception ignored) {
                }
            }

            long deadline = System.currentTimeMillis() + 2100L;
            byte[] buf = new byte[2048];
            while (System.currentTimeMillis() < deadline) {
                try {
                    DatagramPacket resp = new DatagramPacket(buf, buf.length);
                    sock.receive(resp);
                    String body = new String(resp.getData(), 0, resp.getLength(), StandardCharsets.UTF_8);
                    JSONObject obj = new JSONObject(body);
                    int httpPort = obj.optInt("port", 8765);
                    String senderIp = resp.getAddress() != null ? resp.getAddress().getHostAddress() : "";
                    if (senderIp != null && !senderIp.isEmpty() && !senderIp.startsWith("127.")) {
                        found.add("http://" + senderIp + ":" + httpPort);
                    }
                    String primary = obj.optString("primary_url", "");
                    if (!primary.isEmpty()) {
                        found.add(primary);
                    }
                    JSONArray urls = obj.optJSONArray("urls");
                    if (urls != null) {
                        for (int i = 0; i < urls.length(); i++) {
                            String u = urls.optString(i, "");
                            if (!u.isEmpty()) found.add(u);
                        }
                    }
                } catch (Exception timeoutOrParse) {
                    // continue listening until deadline
                }
            }
        } catch (Exception e) {
            appendNativeLog("WARNING", "wifi_discovery", "Loi quet UDP LAN: " + e.getMessage());
        } finally {
            if (sock != null) {
                try {
                    sock.close();
                } catch (Exception ignored) {
                }
            }
        }
        return new ArrayList<>(found);
    }

    private void connectToRemotePcWithCheck(final String rawInput) {
        final String targetUrl = normalizeServerUrl(rawInput);
        if (targetUrl.isEmpty()) {
            Toast.makeText(this, "Vui lòng nhập địa chỉ máy chủ PC (vd: 192.168.1.10:8765).", Toast.LENGTH_SHORT).show();
            return;
        }
        Toast.makeText(this, "Đang kiểm tra kết nối tới " + targetUrl + "...", Toast.LENGTH_SHORT).show();
        appendNativeLog("INFO", "wifi_connect", "Dang kiem tra ket noi PC: " + targetUrl);

        new Thread(() -> {
            String errReason = "";
            boolean ok = false;
            HttpURLConnection conn = null;
            try {
                URL healthUrl = new URL(targetUrl + "/api/health");
                conn = (HttpURLConnection) healthUrl.openConnection();
                conn.setRequestMethod("GET");
                conn.setConnectTimeout(4500);
                conn.setReadTimeout(4500);
                conn.setRequestProperty("User-Agent", "KASAndroid/" + KAS_VERSION);
                int status = conn.getResponseCode();
                if (status == 200) {
                    StringBuilder sb = new StringBuilder();
                    try (BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
                        String line;
                        while ((line = br.readLine()) != null) {
                            sb.append(line);
                        }
                    }
                    String body = sb.toString();
                    if (body.contains("KAS") || body.contains("\"status\"")) {
                        ok = true;
                    } else {
                        errReason = "Máy chủ phản hồi không phải KAS (HTTP 200 nhưng thiếu dữ liệu /api/health).";
                    }
                } else {
                    errReason = "Máy chủ phản hồi mã HTTP " + status;
                }
            } catch (Exception e) {
                errReason = e.getClass().getSimpleName() + ": " + (e.getMessage() != null ? e.getMessage() : "Không thể kết nối");
            } finally {
                if (conn != null) {
                    try {
                        conn.disconnect();
                    } catch (Exception ignored) {
                    }
                }
            }

            final boolean reachable = ok;
            final String finalErr = errReason;
            runOnUiThread(() -> {
                if (reachable) {
                    SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
                    prefs.edit()
                            .putString(KEY_SERVER_MODE, "remote")
                            .putString(KEY_REMOTE_URL, targetUrl)
                            .apply();
                    userManuallyNavigated = true;
                    hideBootOverlaySmoothly();
                    webView.loadUrl(targetUrl);
                    appendNativeLog("INFO", "wifi_connect", "Ket noi PC thanh cong: " + targetUrl);
                    Toast.makeText(MainActivity.this, "Đã kết nối máy chủ PC: " + targetUrl, Toast.LENGTH_SHORT).show();
                } else {
                    appendNativeLog("ERROR", "wifi_connect", "Khong ket noi duoc PC " + targetUrl + " -> " + finalErr);
                    new AlertDialog.Builder(MainActivity.this)
                            .setTitle("Chưa kết nối được tới PC")
                            .setMessage(
                                    "Địa chỉ: " + targetUrl + "\n"
                                            + "Nguyên nhân: " + finalErr + "\n\n"
                                            + "Cách khắc phục nhanh:\n"
                                            + "1. Trên PC, mở KAS → tab Kho Dữ Liệu → bấm 'Bật Chia Sẻ Wi-Fi LAN' (hoặc chạy: kas android serve --port 8765).\n"
                                            + "2. Kiểm tra điện thoại & PC đang dùng chung một mạng Wi-Fi.\n"
                                            + "3. Nếu Windows Firewall chặn, mở cổng TCP 8765 (Private) trên PC."
                            )
                            .setPositiveButton("Đóng (Giữ chế độ hiện tại)", null)
                            .setNeutralButton("Vẫn thử mở URL này", (d, w) -> {
                                SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
                                prefs.edit()
                                        .putString(KEY_SERVER_MODE, "remote")
                                        .putString(KEY_REMOTE_URL, targetUrl)
                                        .apply();
                                userManuallyNavigated = true;
                                hideBootOverlaySmoothly();
                                webView.loadUrl(targetUrl);
                            })
                            .show();
                }
            });
        }, "kas-wifi-check").start();
    }

    public void showServerSwitcherDialog() {
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        String currentMode = prefs.getString(KEY_SERVER_MODE, "local");
        String currentRemote = prefs.getString(KEY_REMOTE_URL, "http://192.168.1.10:8765");

        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(dp(22), dp(14), dp(22), dp(8));

        TextView hint = new TextView(this);
        hint.setText(
                "Chế độ hiện tại: " + ("remote".equals(currentMode) ? "PC Wi-Fi (" + currentRemote + ")" : "Nội bộ trên Android")
                        + "\n\nBấm 'Tự tìm PC cùng Wi-Fi' hoặc nhập địa chỉ IP LAN của PC (trên PC cần bật 'Chia sẻ Wi-Fi LAN' hoặc chạy `kas android serve`):"
        );
        hint.setTextSize(13f);
        hint.setPadding(0, 0, 0, dp(10));
        layout.addView(hint);

        final EditText input = new EditText(this);
        input.setText(currentRemote);
        input.setHint("192.168.1.x:8765");
        input.setSingleLine(true);
        layout.addView(input);

        final TextView scanStatus = new TextView(this);
        scanStatus.setTextSize(12f);
        scanStatus.setTextColor(Color.parseColor("#2F81F7"));
        scanStatus.setPadding(0, dp(6), 0, dp(4));
        layout.addView(scanStatus);

        final Button scanBtn = new Button(this);
        scanBtn.setText("Tự tìm PC cùng Wi-Fi");
        scanBtn.setAllCaps(false);
        scanBtn.setOnClickListener(v -> {
            scanBtn.setEnabled(false);
            scanStatus.setText("Đang quét máy chủ KAS trong mạng Wi-Fi (2 giây)...");
            new Thread(() -> {
                List<String> urls = discoverLanPcServersBlocking();
                runOnUiThread(() -> {
                    scanBtn.setEnabled(true);
                    if (urls.isEmpty()) {
                        scanStatus.setText("Chưa tìm thấy PC nào đang bật Chia sẻ Wi-Fi LAN (cổng 8765/8766). Hãy bật trên PC hoặc nhập IP thủ công.");
                    } else {
                        input.setText(urls.get(0));
                        scanStatus.setText("Đã tìm thấy PC KAS: " + urls.get(0) + (urls.size() > 1 ? " (+" + (urls.size() - 1) + " IP khác)" : ""));
                    }
                });
            }, "kas-lan-scan").start();
        });
        layout.addView(scanBtn);

        new AlertDialog.Builder(this)
                .setTitle("Kết nối Máy chủ KAS (Android / PC Wi-Fi)")
                .setView(layout)
                .setPositiveButton("Kết nối PC qua Wi-Fi", (dialog, which) -> connectToRemotePcWithCheck(input.getText().toString()))
                .setNeutralButton("Dùng Máy Chủ Nội Bộ", (dialog, which) -> {
                    prefs.edit().putString(KEY_SERVER_MODE, "local").apply();
                    userManuallyNavigated = true;
                    hideBootOverlaySmoothly();
                    webView.loadUrl(localServerUrl);
                    appendNativeLog("INFO", "wifi_connect", "Chuyen ve may chu noi bo Android: " + localServerUrl);
                    Toast.makeText(MainActivity.this, "Đang dùng máy chủ KAS nội bộ trên Android.", Toast.LENGTH_SHORT).show();
                })
                .setNegativeButton("Đóng", null)
                .show();
    }

    public void installApkFile(final String localApkPath, final String fallbackUrl) {
        try {
            File apkFile = (localApkPath != null && !localApkPath.trim().isEmpty()) ? new File(localApkPath.trim()) : null;
            if (apkFile == null || !apkFile.isFile() || !apkFile.getName().toLowerCase(Locale.US).endsWith(".apk")) {
                appendNativeLog("WARNING", "updater", "Khong tim thay tep APK cuc bo, chuyen sang tai qua trinh duyet: " + localApkPath);
                if (fallbackUrl != null && (fallbackUrl.startsWith("https://") || fallbackUrl.startsWith("http://"))) {
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(fallbackUrl)));
                } else {
                    Toast.makeText(this, "Không tìm thấy gói APK cập nhật.", Toast.LENGTH_LONG).show();
                }
                return;
            }

            if (!getPackageManager().canRequestPackageInstalls()) {
                pendingApkInstallPath = apkFile.getAbsolutePath();
                appendNativeLog("INFO", "updater", "Yeu cau quyen REQUEST_INSTALL_PACKAGES tu nguoi dung");
                new AlertDialog.Builder(this)
                        .setTitle("Cấp quyền cài đặt bản cập nhật KAS")
                        .setMessage("Android yêu cầu bật quyền 'Cho phép từ nguồn này' cho KAS để cài đặt tự động bản cập nhật mới. Sau khi bật và quay lại, KAS sẽ tự mở trình cài đặt ngay.")
                        .setPositiveButton("Mở Cài đặt Android", (d, w) -> {
                            try {
                                Intent permIntent = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES);
                                permIntent.setData(Uri.parse("package:" + getPackageName()));
                                startActivity(permIntent);
                            } catch (Exception e) {
                                appendNativeLog("ERROR", "updater", "Khong mo duoc man hinh cap quyen cai dat APK: " + e.getMessage());
                            }
                        })
                        .setNegativeButton("Để sau", (d, w) -> pendingApkInstallPath = null)
                        .show();
                return;
            }

            Uri contentUri = KasFileProvider.buildUriForFile(this, apkFile);
            Intent installIntent = new Intent(Intent.ACTION_VIEW);
            installIntent.setDataAndType(contentUri, "application/vnd.android.package-archive");
            installIntent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(installIntent);
            appendNativeLog("INFO", "updater", "Da mo trinh cai dat Android APK thanh cong: " + apkFile.getName());
        } catch (Exception e) {
            appendNativeLog("ERROR", "updater", "Loi mo trinh cai dat APK: " + e.getMessage());
            Toast.makeText(this, "Lỗi mở trình cài đặt APK: " + e.getMessage(), Toast.LENGTH_LONG).show();
            if (fallbackUrl != null && (fallbackUrl.startsWith("https://") || fallbackUrl.startsWith("http://"))) {
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(fallbackUrl)));
                } catch (Exception ignored) {
                }
            }
        }
    }

    public void shareExportedLogFile(final String filename, final String content) {
        try {
            String safeName = (filename == null || filename.trim().isEmpty()) ? "kas-logs.txt" : filename.trim();
            safeName = safeName.replaceAll("[^A-Za-z0-9._-]", "_");
            if (!safeName.endsWith(".txt") && !safeName.endsWith(".json") && !safeName.endsWith(".log")) {
                safeName = safeName + ".txt";
            }
            File dir = new File(getFilesDir(), "kas/data/logs");
            if (!dir.exists()) {
                dir.mkdirs();
            }
            File out = new File(dir, safeName);
            try (FileOutputStream fos = new FileOutputStream(out, false)) {
                fos.write((content != null ? content : "").getBytes(StandardCharsets.UTF_8));
            }
            Uri uri = KasFileProvider.buildUriForFile(this, out);
            Intent share = new Intent(Intent.ACTION_SEND);
            share.setType(safeName.endsWith(".json") ? "application/json" : "text/plain");
            share.putExtra(Intent.EXTRA_STREAM, uri);
            share.putExtra(Intent.EXTRA_SUBJECT, "Nhật kí chẩn đoán KAS v" + KAS_VERSION);
            share.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            startActivity(Intent.createChooser(share, "Xuất / Chia sẻ tệp nhật kí KAS"));
            appendNativeLog("INFO", "logs", "Da xuat & chia se tep nhat ki: " + safeName);
        } catch (Exception e) {
            appendNativeLog("ERROR", "logs", "Loi chia se tep nhat ki: " + e.getMessage());
            Toast.makeText(this, "Không thể chia sẻ tệp nhật kí: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    @SuppressWarnings("deprecation")
    private String computeSigningInfoJson() {
        JSONObject obj = new JSONObject();
        try {
            obj.put("package_name", getPackageName());
            obj.put("sha1", "");
            obj.put("sha256", "");
            Signature[] sigs = null;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                PackageInfo pi = getPackageManager().getPackageInfo(getPackageName(), PackageManager.GET_SIGNING_CERTIFICATES);
                SigningInfo si = pi.signingInfo;
                if (si != null) {
                    sigs = si.hasMultipleSigners() ? si.getApkContentsSigners() : si.getSigningCertificateHistory();
                }
            } else {
                PackageInfo pi = getPackageManager().getPackageInfo(getPackageName(), PackageManager.GET_SIGNATURES);
                sigs = pi.signatures;
            }
            if (sigs != null && sigs.length > 0) {
                byte[] certBytes = sigs[0].toByteArray();
                obj.put("sha1", digestHexColon(certBytes, "SHA-1"));
                obj.put("sha256", digestHexColon(certBytes, "SHA-256"));
            }
        } catch (Exception e) {
            appendNativeLog("WARNING", "signing", "Khong doc duoc van tay chung chi APK: " + e.getMessage());
        }
        return obj.toString();
    }

    private static String digestHexColon(byte[] data, String alg) throws Exception {
        MessageDigest md = MessageDigest.getInstance(alg);
        byte[] digest = md.digest(data);
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < digest.length; i++) {
            if (i > 0) sb.append(':');
            sb.append(String.format(Locale.US, "%02X", digest[i] & 0xFF));
        }
        return sb.toString();
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
            appendNativeLog("ERROR", "storage_perm", "Loi yeu cau quyen bo nho: " + e.getMessage());
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
            return KAS_VERSION;
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
        public void syncSystemTheme(String theme) {
            final boolean isLight = "light".equalsIgnoreCase(theme);
            runOnUiThread(() -> applySystemBarsTheme(isLight));
        }

        @JavascriptInterface
        public void hapticTick() {
            runOnUiThread(() -> {
                if (webView != null) {
                    webView.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK);
                }
            });
        }

        @JavascriptInterface
        public String getDeviceInfo() {
            try {
                JSONObject obj = new JSONObject();
                obj.put("manufacturer", Build.MANUFACTURER != null ? Build.MANUFACTURER : "");
                obj.put("brand", Build.BRAND != null ? Build.BRAND : "");
                obj.put("model", Build.MODEL != null ? Build.MODEL : "Android");
                obj.put("release", Build.VERSION.RELEASE != null ? Build.VERSION.RELEASE : "");
                obj.put("sdk_int", Build.VERSION.SDK_INT);
                obj.put("app_version", KAS_VERSION);
                obj.put("server_mode", getServerMode());
                return obj.toString();
            } catch (Exception e) {
                return "{}";
            }
        }

        @JavascriptInterface
        public String getSigningInfo() {
            return computeSigningInfoJson();
        }

        @JavascriptInterface
        public void installApkUpdate(String localApkPath, String fallbackUrl) {
            runOnUiThread(() -> installApkFile(localApkPath, fallbackUrl));
        }

        @JavascriptInterface
        public String getNativeLogs() {
            return readNativeLogsText();
        }

        @JavascriptInterface
        public void shareExportedLog(String filename, String content) {
            runOnUiThread(() -> shareExportedLogFile(filename, content));
        }

        @JavascriptInterface
        public void openExternalUrl(String url) {
            if (url == null) return;
            final String trimmed = url.trim();
            if (!trimmed.startsWith("https://") && !trimmed.startsWith("http://")) {
                return;
            }
            runOnUiThread(() -> {
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(trimmed)));
                } catch (Exception ignored) {
                }
            });
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
