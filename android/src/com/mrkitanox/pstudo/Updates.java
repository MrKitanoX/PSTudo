package com.mrkitanox.pstudo;

import android.util.Xml;

import org.xmlpull.v1.XmlPullParser;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import javax.net.ssl.HostnameVerifier;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLException;
import javax.net.ssl.SSLSession;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509TrustManager;

/** Updates de jogos direto do servidor da Sony (o mesmo que o PS3 usa). */
public final class Updates {
    private Updates() { }

    static String URL_XML = "https://a0.ww.np.dl.playstation.net/tpl/np/%1$s/%1$s-ver.xml";
    static final String PASTA = "/dev_hdd0/packages";
    static final String[] DISPOSITIVOS = {"/dev_hdd0", "/dev_usb000", "/dev_usb001"};
    /** Certificado raiz público da Sony usado por esse servidor (não vem no Android). */
    static final String CA = "-----BEGIN CERTIFICATE-----\n"
            + "MIID0jCCArqgAwIBAgIBADANBgkqhkiG9w0BAQUFADBUMQswCQYDVQQGEwJKUDEp\n"
            + "MCcGA1UEChMgU29ueSBDb21wdXRlciBFbnRlcnRhaW5tZW50IEluYy4xGjAYBgNV\n"
            + "BAMTEVNDRUkgRE5BUyBSb290IDA1MB4XDTA0MDcxMjA5MDExOVoXDTM3MTIwNjA5\n"
            + "MDExOVowVDELMAkGA1UEBhMCSlAxKTAnBgNVBAoTIFNvbnkgQ29tcHV0ZXIgRW50\n"
            + "ZXJ0YWlubWVudCBJbmMuMRowGAYDVQQDExFTQ0VJIEROQVMgUm9vdCAwNTCCASIw\n"
            + "DQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBANmPeza8PwCqlI7esOGIkoSESnIN\n"
            + "g72ZD3Ut63jy7SdothPIvGBqVZWYkIpqJYJd1I4Nh//IpXQCQL0PnJLrh9BBeowq\n"
            + "Muf5NNq3Us80Ihiu9CvNEAEO18g3OFV1TYdSwQ5zUsk33OUeI7h4aBPDVcZXYeHt\n"
            + "dbPLqe4K8igian5prrAD5S6h28t8aAm+qMWRo+bW25B/841XwDGBP7/IxZv8Yoio\n"
            + "rCo80CVYe6lGoU08eeqQiaHI5zAF281DWZSoVfLjJUEWmEnxqr8aOhszRGePi+Ei\n"
            + "7UQjHDuZX9rLhDI1zAND+BA259tn/iwOqVXe20OccJllHJcG4Ecmd98f5qMCAwEA\n"
            + "AaOBrjCBqzAdBgNVHQ4EFgQUxlahM1tPzoN3YgVEhm0gV7Wv2twwfAYDVR0jBHUw\n"
            + "c4AUxlahM1tPzoN3YgVEhm0gV7Wv2tyhWKRWMFQxCzAJBgNVBAYTAkpQMSkwJwYD\n"
            + "VQQKEyBTb255IENvbXB1dGVyIEVudGVydGFpbm1lbnQgSW5jLjEaMBgGA1UEAxMR\n"
            + "U0NFSSBETkFTIFJvb3QgMDWCAQAwDAYDVR0TBAUwAwEB/zANBgkqhkiG9w0BAQUF\n"
            + "AAOCAQEACZPihjwXA27wJ03tEKcHAeFLi8aBw2ysH4GwuH1dWb3UpuznWOB0iQT1\n"
            + "wQocnEFYCJx5XFEnj4aLWpSHLEq/sSO+my+aPoTEsy20ajF+YLYZm0bZxH50CJYh\n"
            + "rkET4C2aC0XvhGp9k1JQ1o0W6+cFT5LTlXapsq8Btt31t+XDPX7RqGV4WGekt3hM\n"
            + "T7xRc7JWXdAQijIrbYi8mtbM07KEGnPU6IT8C47+0mSurpwLOoWL1tPgo6ePpLNi\n"
            + "c4quUMgh9RXVjeTyXOMmyYdeUm2gt7qErvQONli+6Epmhm0A2khpIMHSpQjTE8gV\n"
            + "rZp42a6+zg1iYy2vFBOmiQ17GRUl0A==\n"
            + "-----END CERTIFICATE-----\n";

    public static class Pacote {
        public String versao = "", sha1 = "", url = "", fw = "";
        public long tamanho;
    }

    public static class Info {
        public String titulo = "";
        public final List<Pacote> pacotes = new ArrayList<Pacote>();
    }

    public static class Jogo {
        public String id, titulo = "", instalado = "";
        Jogo(String id) { this.id = id; }
    }

    public interface Aviso { void texto(String t); }

    // ---------------------------------------------------------------- utilidades
    private static final Pattern ID = Pattern.compile("([A-Z]{4})[-_ ]?(\\d{5})");

    /** "BLUS-30443", "Jogo [blus30443].iso" -> "BLUS30443" (ou null). */
    public static String normalizar(String s) {
        if (s == null) return null;
        Matcher m = ID.matcher(s.toUpperCase(Locale.ROOT));
        return m.find() ? m.group(1) + m.group(2) : null;
    }

    public static int comparar(String a, String b) {
        String[] x = (a == null ? "" : a.trim()).split("\\."), y = (b == null ? "" : b.trim()).split("\\.");
        for (int i = 0; i < Math.max(x.length, y.length); i++) {
            int p = i < x.length ? num(x[i]) : 0, q = i < y.length ? num(y[i]) : 0;
            if (p != q) return p < q ? -1 : 1;
        }
        return 0;
    }

    private static int num(String s) {
        try { return Integer.parseInt(s.trim()); } catch (NumberFormatException e) { return 0; }
    }

    /** "03.5500" -> "3.55". */
    public static String fw(String v) {
        if (v == null || !v.contains(".")) return v == null ? "" : v;
        String[] p = v.split("\\.");
        return num(p[0]) + "." + (p[1].length() > 2 ? p[1].substring(0, 2) : p[1]);
    }

    static boolean daSony(String url) {
        try {
            String h = new URL(url).getHost().toLowerCase(Locale.ROOT);
            return h.equals("playstation.net") || h.endsWith(".playstation.net");
        } catch (IOException e) {
            return false;
        }
    }

    public static String nomePkg(String url) {
        String p = url;
        int q = p.indexOf('?');
        if (q >= 0) p = p.substring(0, q);
        String n = p.substring(p.lastIndexOf('/') + 1);
        try { n = java.net.URLDecoder.decode(n, "UTF-8"); } catch (Exception ignored) { }
        return n.isEmpty() ? "update.pkg" : n;
    }

    // ---------------------------------------------------------------- HTTP
    private static SSLContext ctxSony, ctxSolto;

    private static synchronized SSLContext sony() throws Exception {
        if (ctxSony == null) {
            CertificateFactory cf = CertificateFactory.getInstance("X.509");
            X509Certificate c = (X509Certificate) cf.generateCertificate(new ByteArrayInputStream(CA.getBytes("US-ASCII")));
            KeyStore ks = KeyStore.getInstance(KeyStore.getDefaultType());
            ks.load(null, null);
            ks.setCertificateEntry("sony", c);
            TrustManagerFactory tmf = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
            tmf.init(ks);
            ctxSony = SSLContext.getInstance("TLS");
            ctxSony.init(null, tmf.getTrustManagers(), null);
        }
        return ctxSony;
    }

    /** Sem conferir o certificado: só se o Android recusar o certificado antigo da Sony.
        O .pkg é conferido pelo SHA-1 de qualquer jeito. */
    private static synchronized SSLContext solto() throws Exception {
        if (ctxSolto == null) {
            TrustManager[] t = {new X509TrustManager() {
                public void checkClientTrusted(X509Certificate[] c, String s) { }
                public void checkServerTrusted(X509Certificate[] c, String s) { }
                public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
            }};
            ctxSolto = SSLContext.getInstance("TLS");
            ctxSolto.init(null, t, null);
        }
        return ctxSolto;
    }

    /** Abre o endereço e devolve a conexão já respondida (200). */
    public static HttpURLConnection abrir(String url, int timeoutMs) throws IOException {
        IOException ultimo = null;
        for (int tentativa = 0; tentativa < 2; tentativa++) {
            HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
            c.setConnectTimeout(15000);
            c.setReadTimeout(timeoutMs);
            c.setRequestProperty("User-Agent", "Mozilla/5.0");
            if (c instanceof HttpsURLConnection) {
                try {
                    HttpsURLConnection s = (HttpsURLConnection) c;
                    s.setSSLSocketFactory((tentativa == 0 ? sony() : solto()).getSocketFactory());
                    if (tentativa == 1) s.setHostnameVerifier(new HostnameVerifier() {
                        public boolean verify(String h, SSLSession ss) { return daSony("https://" + h + "/"); }
                    });
                } catch (Exception e) {
                    throw new IOException("TLS: " + e.getMessage());
                }
            }
            try {
                int cod = c.getResponseCode();
                if (cod >= 400) { c.disconnect(); throw new WebMan.ErroHttp(cod); }
                return c;
            } catch (SSLException e) {
                c.disconnect();
                ultimo = e;
                if (!(c instanceof HttpsURLConnection)) throw e;
            }
        }
        throw ultimo;
    }

    public static Info buscar(String id) throws IOException {
        Info r = new Info();
        byte[] dados;
        HttpURLConnection c;
        try {
            c = abrir(String.format(Locale.ROOT, URL_XML, id), 20000);
        } catch (WebMan.ErroHttp e) {
            if (e.codigo == 403 || e.codigo == 404) return r;
            throw e;
        }
        try {
            InputStream in = c.getInputStream();
            ByteArrayOutputStream b = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0 && b.size() < 2 * 1024 * 1024) b.write(buf, 0, n);
            in.close();
            dados = b.toByteArray();
        } finally {
            c.disconnect();
        }
        if (new String(dados, Ftp.LATIN1).trim().isEmpty()) return r;
        try {
            XmlPullParser p = Xml.newPullParser();
            p.setInput(new ByteArrayInputStream(dados), null);
            java.util.Set<String> vistos = new java.util.HashSet<String>();
            boolean noTitulo = false;
            for (int ev = p.getEventType(); ev != XmlPullParser.END_DOCUMENT; ev = p.next()) {
                if (ev == XmlPullParser.START_TAG) {
                    if ("package".equals(p.getName())) {
                        Pacote pk = new Pacote();
                        pk.versao = attr(p, "version");
                        pk.url = attr(p, "url");
                        pk.sha1 = attr(p, "sha1sum").toLowerCase(Locale.ROOT);
                        pk.fw = attr(p, "ps3_system_ver");
                        try { pk.tamanho = Long.parseLong(attr(p, "size")); } catch (NumberFormatException ignored) { }
                        if (!pk.url.isEmpty() && daSony(pk.url) && vistos.add(pk.url)) r.pacotes.add(pk);
                    }
                    noTitulo = "TITLE".equals(p.getName());
                } else if (ev == XmlPullParser.TEXT && noTitulo) {
                    String t = p.getText();
                    if (t != null && !t.trim().isEmpty()) r.titulo = t.trim();
                } else if (ev == XmlPullParser.END_TAG) {
                    noTitulo = false;
                }
            }
        } catch (Exception e) {
            throw new IOException("a Sony respondeu algo que não entendi (" + e.getMessage() + ")");
        }
        Collections.sort(r.pacotes, new Comparator<Pacote>() {
            public int compare(Pacote x, Pacote y) { return comparar(x.versao, y.versao); }
        });
        return r;
    }

    private static String attr(XmlPullParser p, String n) {
        String v = p.getAttributeValue(null, n);
        return v == null ? "" : v;
    }

    // ---------------------------------------------------------------- .pkg aos pedaços, conferindo o SHA-1
    /** O .pkg termina com 32 bytes que guardam o SHA-1 de todo o resto; o XML da Sony traz o mesmo valor. */
    public static class Leitor extends InputStream {
        private final InputStream in;
        private final MessageDigest sha;
        private byte[] cauda = new byte[0];
        public long lidos = 0;
        public volatile boolean cancelado = false;

        public Leitor(InputStream in) throws IOException {
            this.in = in;
            try { sha = MessageDigest.getInstance("SHA-1"); } catch (Exception e) { throw new IOException(e.getMessage()); }
        }

        @Override public int read() throws IOException {
            byte[] b = new byte[1];
            int n = read(b, 0, 1);
            return n <= 0 ? -1 : b[0] & 0xff;
        }

        @Override public int read(byte[] b, int off, int len) throws IOException {
            if (cancelado) throw new IOException("cancelado");
            int n = in.read(b, off, len);
            if (n > 0) {
                byte[] junto = new byte[cauda.length + n];
                System.arraycopy(cauda, 0, junto, 0, cauda.length);
                System.arraycopy(b, off, junto, cauda.length, n);
                int corpo = Math.max(0, junto.length - 32);
                sha.update(junto, 0, corpo);
                cauda = new byte[junto.length - corpo];
                System.arraycopy(junto, corpo, cauda, 0, cauda.length);
                lidos += n;
            }
            return n;
        }

        @Override public void close() throws IOException { in.close(); }

        public void conferir(Pacote pk) throws IOException {
            if (pk.tamanho > 0 && lidos != pk.tamanho)
                throw new IOException("o download veio incompleto");
            String calc = hex(sha.digest(), 20);
            String fim = cauda.length >= 20 ? hex(cauda, 20) : "";
            if (!calc.equals(pk.sha1) && !calc.equals(fim))
                throw new IOException("o arquivo baixado veio corrompido (o SHA-1 não confere)");
        }
    }

    static String hex(byte[] b, int n) {
        StringBuilder s = new StringBuilder();
        for (int i = 0; i < n && i < b.length; i++) s.append(String.format(Locale.ROOT, "%02x", b[i] & 0xff));
        return s.toString();
    }

    // ---------------------------------------------------------------- jogos do PS3
    private static Map<String, String> sfoRemoto(Ftp f, String caminho) {
        try { return Sfo.ler(f.lerPedaco(caminho, 0, 65536)); } catch (IOException e) { return new LinkedHashMap<String, String>(); }
    }

    private static String v(Map<String, String> m, String k) {
        String s = m.get(k);
        return s == null ? "" : s;
    }

    public static String versaoInstalada(Ftp f, String id) {
        Map<String, String> s = sfoRemoto(f, "/dev_hdd0/game/" + id + "/PARAM.SFO");
        String cat = v(s, "CATEGORY").toUpperCase(Locale.ROOT);
        return cat.equals("GD") || cat.equals("HG") || cat.equals("DG") ? v(s, "APP_VER") : "";
    }

    /** Jogos em pastas GAMES, ISOs e o que estiver instalado em /dev_hdd0/game. */
    public static List<Jogo> listarJogos(Ftp f, Aviso av) {
        Map<String, Jogo> jogos = new LinkedHashMap<String, Jogo>();
        for (String dev : DISPOSITIVOS) {
            List<Ftp.Item> pastas;
            try { pastas = f.listar(dev + "/GAMES"); } catch (IOException e) { pastas = new ArrayList<Ftp.Item>(); }
            for (Ftp.Item it : pastas) {
                if (!it.pasta) continue;
                if (av != null) av.texto("Lendo " + Ftp.legivel(it.nome) + "…");
                Map<String, String> s = sfoRemoto(f, dev + "/GAMES/" + it.nome + "/PS3_GAME/PARAM.SFO");
                String id = normalizar(v(s, "TITLE_ID"));
                if (id == null) id = normalizar(it.nome);
                String t = v(s, "TITLE");
                juntar(jogos, id, t.isEmpty() ? Ftp.legivel(it.nome) : t, v(s, "APP_VER"), true);
            }
            List<Ftp.Item> isos;
            try { isos = f.listar(dev + "/PS3ISO"); } catch (IOException e) { isos = new ArrayList<Ftp.Item>(); }
            for (Ftp.Item it : isos) {
                String baixo = it.nome.toLowerCase(Locale.ROOT);
                if (it.pasta || !(baixo.endsWith(".iso") || baixo.endsWith(".iso.0"))) continue;
                if (av != null) av.texto("Lendo " + Ftp.legivel(it.nome) + "…");
                String id = null;
                try {     // a ISO do PS3 guarda o código do jogo no setor 1 (posição 0x810)
                    id = normalizar(new String(f.lerPedaco(dev + "/PS3ISO/" + it.nome, 0x810, 10), Ftp.LATIN1));
                } catch (IOException ignored) { }
                if (id == null) id = normalizar(it.nome);
                String t = Ftp.legivel(it.nome).replaceAll("\\s*[\\[(][A-Za-z]{4}-?\\d{5}[\\])]\\s*", " ")
                        .replaceAll("(?i)\\.iso(\\.0)?$", "").trim();
                juntar(jogos, id, t, "", true);
            }
        }
        List<Ftp.Item> inst;
        try { inst = f.listar("/dev_hdd0/game"); } catch (IOException e) { inst = new ArrayList<Ftp.Item>(); }
        for (Ftp.Item it : inst) {
            String id = normalizar(it.nome);
            if (!it.pasta || id == null || !id.equals(it.nome.toUpperCase(Locale.ROOT))) continue;
            if (av != null) av.texto("Lendo " + it.nome + "…");
            Map<String, String> s = sfoRemoto(f, "/dev_hdd0/game/" + it.nome + "/PARAM.SFO");
            String cat = v(s, "CATEGORY").toUpperCase(Locale.ROOT);
            if (!(cat.equals("GD") || cat.equals("HG") || cat.equals("DG"))) continue;
            juntar(jogos, id, v(s, "TITLE"), v(s, "APP_VER"), false);
        }
        List<Jogo> l = new ArrayList<Jogo>(jogos.values());
        Collections.sort(l, new Comparator<Jogo>() {
            public int compare(Jogo x, Jogo y) {
                int c = (x.titulo.isEmpty() ? x.id : x.titulo).compareToIgnoreCase(y.titulo.isEmpty() ? y.id : y.titulo);
                return c != 0 ? c : x.id.compareTo(y.id);
            }
        });
        return l;
    }

    private static void juntar(Map<String, Jogo> jogos, String id, String titulo, String versao, boolean principal) {
        if (id == null) return;
        Jogo j = jogos.get(id);
        if (j == null) { j = new Jogo(id); jogos.put(id, j); }
        if (titulo != null && !titulo.isEmpty() && (j.titulo.isEmpty() || principal)) j.titulo = titulo;
        if (versao != null && !versao.isEmpty() && comparar(versao, j.instalado.isEmpty() ? "0" : j.instalado) > 0)
            j.instalado = versao;
    }

    // ---------------------------------------------------------------- instalar .pkg pelo webMAN
    public interface Parar { void checar() throws IOException; }
    public interface Pronto { boolean pronto(Ftp f); }

    /** Confere se a conexão FTP ainda responde; se caiu, conecta de novo. */
    public static Ftp garantirConexao(MainActivity a, Ftp f) {
        try { f.cmd("NOOP"); return f; } catch (IOException e) {
            f.fechar();
            try { return a.conectar(); } catch (IOException e2) { return f; }
        }
    }

    /** Pede ao webMAN para instalar um .pkg que já está no PS3 e espera terminar (o webMAN apaga o arquivo
        depois de instalar; o PS3 mostra o andamento na tela). false = este webMAN não instala .pkg sozinho. */
    public static boolean instalarPkg(MainActivity a, Ftp[] con, String caminho, String nome, Parar parar, Pronto pronto)
            throws IOException {
        try {
            WebMan.http(a.ip(), "install.ps3" + WebMan.url(caminho), 30000);
        } catch (WebMan.ErroHttp e) {
            if (e.codigo == 400) throw new IOException("o PS3 recusou instalar " + nome
                    + ". Saia do jogo (fique no XMB) e confira o espaço livre.");
            return false;
        } catch (java.net.SocketTimeoutException ignored) {
            // o pedido chegou; o PS3 só demorou para responder
        }
        long limite = System.currentTimeMillis() + 30 * 60 * 1000L;
        while (System.currentTimeMillis() < limite) {
            parar.checar();
            try { Thread.sleep(3000); } catch (InterruptedException e) { break; }
            try {
                boolean existe = con[0].existeOuErro(caminho);
                if (!existe || (pronto != null && pronto.pronto(con[0]))) {
                    try { Thread.sleep(2000); } catch (InterruptedException ignored) { }
                    return true;
                }
            } catch (IOException e) {
                con[0] = garantirConexao(a, con[0]);     // o PS3 fica ocupado instalando
            }
        }
        throw new IOException("a instalação de " + nome + " não terminou em 30 minutos");
    }
}
