package io.github.kariusnocr.kas;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.util.List;

/**
 * Pure Android SDK ContentProvider (zero AndroidX dependency) serving read-only URIs strictly within:
 *   - <filesDir>/kas/data/updates/  (verified KAS APK updates)
 *   - <filesDir>/kas/data/logs/     (exported diagnostic log files)
 */
public class KasFileProvider extends ContentProvider {
    public static final String AUTHORITY = "io.github.kariusnocr.kas.provider";

    public static Uri buildUriForFile(Context ctx, File targetFile) throws IOException {
        File dataRoot = new File(ctx.getFilesDir(), "kas/data").getCanonicalFile();
        File updatesRoot = new File(dataRoot, "updates").getCanonicalFile();
        File logsRoot = new File(dataRoot, "logs").getCanonicalFile();
        File target = targetFile.getCanonicalFile();

        String targetPath = target.getPath();
        String updatesPrefix = updatesRoot.getPath() + File.separator;
        String logsPrefix = logsRoot.getPath() + File.separator;

        if (targetPath.startsWith(updatesPrefix)) {
            String rel = targetPath.substring(updatesPrefix.length()).replace(File.separatorChar, '/');
            return Uri.parse("content://" + AUTHORITY + "/updates/" + Uri.encode(rel, "/"));
        }
        if (targetPath.startsWith(logsPrefix)) {
            String rel = targetPath.substring(logsPrefix.length()).replace(File.separatorChar, '/');
            return Uri.parse("content://" + AUTHORITY + "/logs/" + Uri.encode(rel, "/"));
        }
        throw new SecurityException("Tệp nằm ngoài phạm vi chia sẻ an toàn của KAS: " + targetPath);
    }

    private File resolveSafeFile(Uri uri) throws FileNotFoundException {
        Context ctx = getContext();
        if (ctx == null || uri == null) {
            throw new FileNotFoundException("Invalid context or URI");
        }
        List<String> segs = uri.getPathSegments();
        if (segs == null || segs.size() < 2) {
            throw new FileNotFoundException("Invalid URI path: " + uri);
        }
        String bucket = segs.get(0);
        if (!"updates".equals(bucket) && !"logs".equals(bucket)) {
            throw new SecurityException("Disallowed bucket: " + bucket);
        }
        try {
            File root = new File(ctx.getFilesDir(), "kas/data/" + bucket).getCanonicalFile();
            File cur = root;
            for (int i = 1; i < segs.size(); i++) {
                String seg = segs.get(i);
                if (seg == null || seg.isEmpty() || ".".equals(seg) || "..".equals(seg) || seg.contains("/") || seg.contains("\\")) {
                    throw new SecurityException("Invalid path segment");
                }
                cur = new File(cur, seg);
            }
            File resolved = cur.getCanonicalFile();
            String rootPrefix = root.getPath() + File.separator;
            if (!resolved.getPath().startsWith(rootPrefix) || !resolved.isFile()) {
                throw new FileNotFoundException("File not found or outside sandbox: " + resolved.getPath());
            }
            return resolved;
        } catch (IOException e) {
            throw new FileNotFoundException(e.getMessage());
        }
    }

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public Cursor query(Uri uri, String[] projection, String selection, String[] selectionArgs, String sortOrder) {
        try {
            File file = resolveSafeFile(uri);
            String[] cols = (projection != null && projection.length > 0)
                    ? projection
                    : new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE};
            MatrixCursor cursor = new MatrixCursor(cols, 1);
            Object[] row = new Object[cols.length];
            for (int i = 0; i < cols.length; i++) {
                if (OpenableColumns.DISPLAY_NAME.equals(cols[i])) {
                    row[i] = file.getName();
                } else if (OpenableColumns.SIZE.equals(cols[i])) {
                    row[i] = file.length();
                } else {
                    row[i] = null;
                }
            }
            cursor.addRow(row);
            return cursor;
        } catch (Exception e) {
            return new MatrixCursor(new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE}, 0);
        }
    }

    @Override
    public String getType(Uri uri) {
        if (uri == null || uri.getLastPathSegment() == null) {
            return "application/octet-stream";
        }
        String name = uri.getLastPathSegment().toLowerCase();
        if (name.endsWith(".apk")) {
            return "application/vnd.android.package-archive";
        }
        if (name.endsWith(".json")) {
            return "application/json";
        }
        if (name.endsWith(".txt") || name.endsWith(".log")) {
            return "text/plain";
        }
        return "application/octet-stream";
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (mode != null && mode.contains("w")) {
            throw new SecurityException("Read-only provider");
        }
        File file = resolveSafeFile(uri);
        return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        throw new UnsupportedOperationException("Read-only provider");
    }

    @Override
    public int delete(Uri uri, String selection, String[] selectionArgs) {
        throw new UnsupportedOperationException("Read-only provider");
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] selectionArgs) {
        throw new UnsupportedOperationException("Read-only provider");
    }
}
