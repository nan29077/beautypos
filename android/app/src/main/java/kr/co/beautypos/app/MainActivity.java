package kr.co.beautypos.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.Toast;

import java.net.URI;
import java.net.URISyntaxException;

public class MainActivity extends Activity {
    private static final String PREFS = "beautypos_preferences";
    private static final String SERVER_URL = "server_url";
    private static final String DEFAULT_URL = "https://ad-pay.co.kr";
    private static final int FILE_CHOOSER_REQUEST = 1001;
    private static final int MENU_HOME = 1;
    private static final int MENU_REFRESH = 2;
    private static final int MENU_SERVER = 3;

    private WebView webView;
    private ProgressBar progressBar;
    private ValueCallback<Uri[]> fileCallback;
    private String serverUrl;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webView);
        progressBar = findViewById(R.id.progressBar);
        serverUrl = getPreferencesStore().getString(SERVER_URL, DEFAULT_URL);
        configureWebView();

        if (savedInstanceState != null) {
            webView.restoreState(savedInstanceState);
        } else {
            openLogin();
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void configureWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        settings.setUserAgentString(settings.getUserAgentString() + " BeautyPOS-Android/1.0");

        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(webView, true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                progressBar.setVisibility(View.VISIBLE);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                progressBar.setVisibility(View.GONE);
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (isAppServer(uri)) return false;
                openExternal(uri);
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    progressBar.setVisibility(View.GONE);
                    Toast.makeText(MainActivity.this,
                            "서버에 연결할 수 없습니다. 메뉴에서 서버 주소를 확인해 주세요.",
                            Toast.LENGTH_LONG).show();
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int progress) {
                progressBar.setProgress(progress);
                progressBar.setVisibility(progress == 100 ? View.GONE : View.VISIBLE);
            }

            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                             FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                try {
                    startActivityForResult(params.createIntent(), FILE_CHOOSER_REQUEST);
                    return true;
                } catch (Exception ex) {
                    fileCallback = null;
                    Toast.makeText(MainActivity.this, "파일 선택기를 열 수 없습니다.", Toast.LENGTH_SHORT).show();
                    return false;
                }
            }
        });
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(Menu.NONE, MENU_HOME, Menu.NONE, "홈").setShowAsAction(MenuItem.SHOW_AS_ACTION_IF_ROOM);
        menu.add(Menu.NONE, MENU_REFRESH, Menu.NONE, "새로고침").setShowAsAction(MenuItem.SHOW_AS_ACTION_IF_ROOM);
        menu.add(Menu.NONE, MENU_SERVER, Menu.NONE, "서버 주소").setShowAsAction(MenuItem.SHOW_AS_ACTION_NEVER);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        if (item.getItemId() == MENU_HOME) {
            openLogin();
            return true;
        }
        if (item.getItemId() == MENU_REFRESH) {
            webView.reload();
            return true;
        }
        if (item.getItemId() == MENU_SERVER) {
            showServerDialog(false);
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    private void showServerDialog(boolean required) {
        LinearLayout container = new LinearLayout(this);
        container.setOrientation(LinearLayout.VERTICAL);
        int padding = Math.round(24 * getResources().getDisplayMetrics().density);
        container.setPadding(padding, 0, padding, 0);

        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setHint("예: http://192.168.0.10:3000");
        input.setText(serverUrl.isEmpty() ? DEFAULT_URL : serverUrl);
        input.setSelectAllOnFocus(true);
        container.addView(input);

        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("BeautyPOS 서버 주소")
                .setMessage("기본 운영 서버는 https://ad-pay.co.kr 입니다. 개발 서버를 쓰려면 PC와 휴대폰을 같은 Wi-Fi에 연결한 뒤 PC의 IPv4 주소와 3000 포트를 입력하세요.")
                .setView(container)
                .setPositiveButton("연결", null)
                .setNegativeButton(required ? "종료" : "취소", (d, which) -> {
                    if (required) finish();
                })
                .create();

        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String normalized = normalizeServerUrl(input.getText().toString());
            if (normalized == null) {
                input.setError("http:// 또는 https://로 시작하는 올바른 주소를 입력하세요.");
                return;
            }
            serverUrl = normalized;
            getPreferencesStore().edit().putString(SERVER_URL, serverUrl).apply();
            dialog.dismiss();
            openLogin();
        }));
        dialog.setCancelable(!required);
        dialog.show();
    }

    private String normalizeServerUrl(String raw) {
        String value = raw == null ? "" : raw.trim();
        while (value.endsWith("/")) value = value.substring(0, value.length() - 1);
        try {
            URI uri = new URI(value);
            String scheme = uri.getScheme();
            if (("http".equalsIgnoreCase(scheme) || "https".equalsIgnoreCase(scheme))
                    && uri.getHost() != null) return value;
        } catch (URISyntaxException ignored) {
        }
        return null;
    }

    private boolean isAppServer(Uri uri) {
        if (serverUrl == null || serverUrl.isEmpty()) return false;
        Uri base = Uri.parse(serverUrl);
        return equalsIgnoreCase(base.getScheme(), uri.getScheme())
                && equalsIgnoreCase(base.getHost(), uri.getHost())
                && effectivePort(base) == effectivePort(uri);
    }

    private int effectivePort(Uri uri) {
        if (uri.getPort() != -1) return uri.getPort();
        return "https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80;
    }

    private boolean equalsIgnoreCase(String a, String b) {
        return a != null && b != null && a.equalsIgnoreCase(b);
    }

    private void openExternal(Uri uri) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (Exception ex) {
            Toast.makeText(this, "외부 링크를 열 수 없습니다.", Toast.LENGTH_SHORT).show();
        }
    }

    private void openLogin() {
        if (serverUrl == null || serverUrl.isEmpty()) {
            showServerDialog(true);
            return;
        }
        webView.loadUrl(serverUrl + "/static/login.html");
    }

    private SharedPreferences getPreferencesStore() {
        return getSharedPreferences(PREFS, MODE_PRIVATE);
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        webView.saveState(outState);
        super.onSaveInstanceState(outState);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == FILE_CHOOSER_REQUEST && fileCallback != null) {
            Uri[] result = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
            fileCallback.onReceiveValue(result);
            fileCallback = null;
        }
    }
}
