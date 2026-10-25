package com.mrkitanox.pstudo;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

/** Lê o nome do jogo (TITLE) de um PARAM.SFO. */
public final class Sfo {
    private Sfo() { }

    private static int u32(byte[] d, int o) {
        return (d[o] & 0xff) | (d[o + 1] & 0xff) << 8 | (d[o + 2] & 0xff) << 16 | (d[o + 3] & 0xff) << 24;
    }

    private static int u16(byte[] d, int o) { return (d[o] & 0xff) | (d[o + 1] & 0xff) << 8; }

    public static String titulo(InputStream in) {
        try {
            ByteArrayOutputStream b = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while (b.size() < 65536 && (n = in.read(buf)) > 0) b.write(buf, 0, n);
            byte[] d = b.toByteArray();
            if (d.length < 20 || d[0] != 0 || d[1] != 'P' || d[2] != 'S' || d[3] != 'F') return null;
            int kIni = u32(d, 8), dIni = u32(d, 12), qtd = u32(d, 16);
            for (int i = 0; i < qtd; i++) {
                int e = 20 + i * 16;
                int kOff = u16(d, e), dLen = u32(d, e + 4), dOff = u32(d, e + 12);
                int k = kIni + kOff, fim = k;
                while (fim < d.length && d[fim] != 0) fim++;
                if (new String(d, k, fim - k, Ftp.LATIN1).equals("TITLE")) {
                    int a = dIni + dOff, z = a;
                    while (z < a + dLen && z < d.length && d[z] != 0) z++;
                    return new String(d, a, z - a, Ftp.UTF8).replace('\n', ' ').trim();
                }
            }
        } catch (IOException | RuntimeException ignored) {
        } finally {
            try { in.close(); } catch (Exception ignored) { }
        }
        return null;
    }
}
