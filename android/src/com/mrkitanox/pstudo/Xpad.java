package com.mrkitanox.pstudo;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/** XPAD Revolution: baixar, instalar, ligar sozinho depois do HEN, controles registrados e desinstalar. */
public final class Xpad {
    private Xpad() { }

    public static final String DIR = "/dev_hdd0/plugins/ps3xpad";
    public static final String VSH = DIR + "/xpad_vsh_autodiscovery.sprx";
    public static final String DEVICES = DIR + "/xpad_devices.txt";
    public static final String ANALOG = DIR + "/xpad_analog.txt";
    public static final String API = "https://api.github.com/repos/GabaRSk/XPAD-Revolution/releases/latest";
    public static final String ZIP_PADRAO =
            "https://github.com/GabaRSk/XPAD-Revolution/releases/latest/download/XPAD-Revolution-v1.0.0.zip";
    public static final int LIMITE_DEVICES = 24;
    public static final int ATRASO = 15;

    public static final String AUTOEXEC = "/dev_hdd0/autoexec.bat";
    public static final String BLOCO_INI = "# >>> PSTudo: XPAD Revolution";
    public static final String BLOCO_FIM = "# <<< PSTudo: XPAD Revolution";
    public static final String[] LISTAS_BOOT = {"/dev_hdd0/boot_plugins.txt", "/dev_hdd0/boot_plugins_nocobra.txt",
            "/dev_hdd0/boot_plugins_dex.txt", "/dev_hdd0/boot_plugins_nocobra_dex.txt", "/dev_hdd0/mamba_plugins.txt",
            "/dev_hdd0/prx_plugins.txt", "/dev_hdd0/game/PRXLOADER/USRDIR/plugins.txt"};

    public static final String[][] TIPOS = {{"XTYPE_XBOX360", "Xbox 360 / XInput"}, {"PTYPE_PS4", "DualShock 4"},
            {"PTYPE_PS5", "DualSense"}, {"XTYPE_XBOX360W", "Receptor sem fio Xbox 360"}};

    public static String nomeTipo(String t) {
        for (String[] x : TIPOS) if (x[0].equals(t)) return x[1];
        return t;
    }

    // ---------------------------------------------------------------- download e ZIP
    private static byte[] baixarUrl(String url, int timeout) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setRequestProperty("User-Agent", "PSTudo");
        c.setConnectTimeout(15000);
        c.setReadTimeout(timeout);
        c.setInstanceFollowRedirects(true);
        try {
            if (c.getResponseCode() >= 400) throw new IOException("HTTP " + c.getResponseCode());
            InputStream in = c.getInputStream();
            ByteArrayOutputStream b = new ByteArrayOutputStream();
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) b.write(buf, 0, n);
            in.close();
            return b.toByteArray();
        } finally {
            c.disconnect();
        }
    }

    public static byte[] baixarZip() throws IOException {
        String url = ZIP_PADRAO;
        try {
            String json = new String(baixarUrl(API, 15000), Ftp.UTF8);
            Matcher m = Pattern.compile("\"browser_download_url\"\\s*:\\s*\"([^\"]+\\.zip)\"").matcher(json);
            if (m.find()) url = m.group(1);
        } catch (IOException ignored) { }
        return baixarUrl(url, 60000);
    }

    public static class Pacote {
        public final Map<String, byte[]> arquivos = new LinkedHashMap<String, byte[]>();
        public String versao = "";
    }

    private static String hex(byte[] b) {
        StringBuilder s = new StringBuilder();
        for (byte x : b) s.append(String.format("%02x", x & 0xff));
        return s.toString();
    }

    public static Pacote abrirZip(byte[] zip) throws IOException {
        Pacote p = new Pacote();
        Map<String, byte[]> todos = new LinkedHashMap<String, byte[]>();
        ZipInputStream z = new ZipInputStream(new ByteArrayInputStream(zip));
        ZipEntry e;
        byte[] buf = new byte[65536];
        while ((e = z.getNextEntry()) != null) {
            if (e.isDirectory()) continue;
            ByteArrayOutputStream b = new ByteArrayOutputStream();
            int n;
            while ((n = z.read(buf)) > 0) b.write(buf, 0, n);
            String nome = e.getName().replace('\\', '/');
            todos.put(nome, b.toByteArray());
            String[] partes = nome.split("/");
            if (partes.length >= 2 && partes[partes.length - 2].equals("ps3xpad")) p.arquivos.put(partes[partes.length - 1], b.toByteArray());
        }
        z.close();
        if (!p.arquivos.containsKey("xpad_vsh_autodiscovery.sprx"))
            throw new IOException("Esse ZIP não parece ser do XPAD Revolution.");
        for (Map.Entry<String, byte[]> t : todos.entrySet()) {
            String base = t.getKey().substring(t.getKey().lastIndexOf('/') + 1).toUpperCase(Locale.ROOT);
            if (base.equals("SHA256SUMS.TXT")) {
                try {
                    MessageDigest md = MessageDigest.getInstance("SHA-256");
                    for (String linha : new String(t.getValue(), Ftp.UTF8).split("\n")) {
                        String[] q = linha.trim().split("\\s+");
                        if (q.length != 2) continue;
                        String n = q[1].substring(q[1].lastIndexOf('/') + 1);
                        byte[] d = p.arquivos.get(n);
                        if (d != null && !hex(md.digest(d)).equalsIgnoreCase(q[0]))
                            throw new IOException("O arquivo " + n + " do ZIP está corrompido. Baixe de novo.");
                    }
                } catch (java.security.NoSuchAlgorithmException ignored) { }
            } else if (base.equals("VERSION.TXT")) {
                p.versao = new String(t.getValue(), Ftp.UTF8).split("\n")[0].trim();
            }
        }
        return p;
    }

    /** Copia para o PS3. Arquivos .txt que já existem (configurações do usuário) são mantidos. */
    public static List<String> instalar(Ftp ftp, Pacote p) throws IOException {
        ftp.criarPasta("/dev_hdd0/plugins");
        ftp.criarPasta(DIR);
        List<String> mantidos = new ArrayList<String>();
        for (Map.Entry<String, byte[]> a : p.arquivos.entrySet()) {
            String remoto = DIR + "/" + a.getKey();
            if (a.getKey().toLowerCase(Locale.ROOT).endsWith(".txt") && ftp.existe(remoto)) {
                mantidos.add(a.getKey());
                continue;
            }
            ftp.enviar(remoto, a.getValue());
        }
        return mantidos;
    }

    // ---------------------------------------------------------------- analógico
    public static int[] lerAnalog(Ftp ftp) {
        if (!ftp.existe(ANALOG)) return null;
        String t = ftp.lerTextoOuVazio(ANALOG);
        return new int[]{valor(t, "ANALOG_SATURATION", 80), valor(t, "ANALOG_DEADZONE", 4)};
    }

    private static int valor(String t, String chave, int padrao) {
        Matcher m = Pattern.compile("(?m)^\\s*" + chave + "\\s*=\\s*(\\d+)").matcher(t);
        return m.find() ? Integer.parseInt(m.group(1)) : padrao;
    }

    public static void gravarAnalog(Ftp ftp, int sat, int dz) throws IOException {
        String t = ftp.lerTextoOuVazio(ANALOG);
        java.nio.charset.Charset cod = ftp.codUltimo;
        String[][] pares = {{"ANALOG_SATURATION", String.valueOf(sat)}, {"ANALOG_DEADZONE", String.valueOf(dz)}};
        for (String[] kv : pares) {
            Pattern p = Pattern.compile("(?m)^(\\s*" + kv[0] + "\\s*=\\s*).*$");
            Matcher m = p.matcher(t);
            if (m.find()) t = m.replaceFirst("$1" + kv[1]);
            else t = t.replaceAll("\\n+$", "") + "\n" + kv[0] + " = " + kv[1] + "\n";
        }
        ftp.gravarTexto(ANALOG, t, cod);
    }

    // ---------------------------------------------------------------- ligar sozinho depois do HEN
    public static String bloco() {
        StringBuilder s = new StringBuilder();
        s.append(BLOCO_INI).append(" (carrega ").append(ATRASO).append(" s depois do HEN; criado pelo PSTudo)\n");
        s.append("wait xmb\n");
        int r = ATRASO;
        while (r > 0) { int w = Math.min(9, r); s.append("wait ").append(w).append('\n'); r -= w; }
        s.append("/loadprx.ps3?slot=0&prx=").append(VSH).append('\n');
        s.append(BLOCO_FIM).append('\n');
        return s.toString();
    }

    public static String tirarBloco(String t) {
        int i = t.indexOf(BLOCO_INI);
        if (i < 0) return t;
        int f = t.indexOf(BLOCO_FIM, i);
        if (f < 0) return t.substring(0, i);
        String depois = t.substring(f + BLOCO_FIM.length()).replaceFirst("^[\\r\\n]+", "");
        return t.substring(0, i) + depois;
    }

    public static boolean inicioLigado(Ftp ftp) { return ftp.lerTextoOuVazio(AUTOEXEC).contains(BLOCO_INI); }

    public static boolean ehXpad(String s) {
        String t = s.toLowerCase(Locale.ROOT);
        return t.contains("ps3xpad") || t.contains("xpad_vsh") || t.contains("xpad_game") || t.contains("/xpad.sprx");
    }

    private static void salvarCopia(File pasta, String nome, byte[] dados) {
        try {
            if (!pasta.exists()) pasta.mkdirs();
            FileOutputStream o = new FileOutputStream(new File(pasta, nome));
            o.write(dados);
            o.close();
        } catch (IOException ignored) { }
    }

    /** Tira as linhas do XPAD das listas do boot (cópia antes). Devolve quantas linhas saíram. */
    public static int tirarDasListas(Ftp ftp, File backup) throws IOException {
        int total = 0;
        for (String lista : LISTAS_BOOT) {
            if (!ftp.existe(lista)) continue;
            String t = ftp.lerTexto(lista);
            java.nio.charset.Charset cod = ftp.codUltimo;
            StringBuilder sobra = new StringBuilder();
            int tiradas = 0;
            for (String l : t.split("(?<=\\n)")) {
                if (ehXpad(l)) tiradas++; else sobra.append(l);
            }
            if (tiradas > 0) {
                salvarCopia(backup, lista.replaceAll("^/+", "").replace('/', '_'), t.getBytes(cod));
                ftp.gravarTexto(lista, sobra.toString(), cod);
                total += tiradas;
            }
        }
        return total;
    }

    /** Liga o XPAD 15 s depois do HEN pelo autoexec.bat do webMAN e tira ele das listas do boot. */
    public static int ligarInicio(Ftp ftp, File backup) throws IOException {
        String t = tirarBloco(ftp.lerTextoOuVazio(AUTOEXEC));
        java.nio.charset.Charset cod = ftp.codUltimo;
        if (!t.isEmpty() && !t.endsWith("\n")) t += "\n";
        ftp.gravarTexto(AUTOEXEC, t + bloco(), cod);
        return tirarDasListas(ftp, backup);
    }

    public static boolean desligarInicio(Ftp ftp) throws IOException {
        String t = ftp.lerTextoOuVazio(AUTOEXEC);
        java.nio.charset.Charset cod = ftp.codUltimo;
        if (!t.contains(BLOCO_INI)) return false;
        String sobra = tirarBloco(t);
        if (sobra.trim().isEmpty()) ftp.apagarArquivo(AUTOEXEC);
        else ftp.gravarTexto(AUTOEXEC, sobra, cod);
        return true;
    }

    /** Apaga tudo do XPAD do PS3. Devolve {arquivos, linhas do boot, 1 se tirou o início automático}. */
    public static int[] desinstalar(Ftp ftp, File backup) throws IOException {
        int arquivos = 0;
        List<Ftp.Item> itens = null;
        try { itens = ftp.listar(DIR); } catch (IOException ignored) { }
        if (itens != null) {
            for (Ftp.Item it : itens) {
                if (it.pasta) continue;
                String n = it.nome.toLowerCase(Locale.ROOT);
                if (n.endsWith(".txt") || n.endsWith(".ini") || n.endsWith(".cfg"))
                    salvarCopia(backup, Ftp.legivel(it.nome), ftp.baixar(Caminhos.juntar(DIR, it.nome)));
                arquivos++;
            }
            ftp.apagar(DIR, true);
        }
        try {
            for (Ftp.Item it : ftp.listar("/dev_hdd0/plugins")) {
                String n = it.nome.toLowerCase(Locale.ROOT);
                if (!it.pasta && n.endsWith(".sprx") && (n.startsWith("xpad") || ehXpad("/" + n))) {
                    ftp.apagarArquivo(Caminhos.juntar("/dev_hdd0/plugins", it.nome));
                    arquivos++;
                }
            }
        } catch (IOException ignored) { }
        int linhas = tirarDasListas(ftp, backup);
        boolean auto = desligarInicio(ftp);
        return new int[]{arquivos, linhas, auto ? 1 : 0};
    }

    // ---------------------------------------------------------------- controles registrados
    public static class Controle {
        public final int vid, pid;
        public final String nome, tipo;
        public Controle(int vid, int pid, String nome, String tipo) { this.vid = vid; this.pid = pid; this.nome = nome; this.tipo = tipo; }
        public String chave() { return vid + ":" + pid; }
    }

    private static int[] vidPid(String linha) {
        String util = linha.split("#", 2)[0].trim();
        String[] p = util.split(",");
        if (p.length < 4) return null;
        try {
            return new int[]{Integer.parseInt(p[0].trim().toLowerCase(Locale.ROOT).replaceFirst("^0x", ""), 16),
                    Integer.parseInt(p[1].trim().toLowerCase(Locale.ROOT).replaceFirst("^0x", ""), 16)};
        } catch (NumberFormatException e) {
            return null;
        }
    }

    public static List<Controle> registrados(String texto) {
        List<Controle> l = new ArrayList<Controle>();
        Set<String> vistos = new HashSet<String>();
        for (String linha : texto.split("\n")) {
            int[] vp = vidPid(linha);
            if (vp == null) continue;
            String[] p = linha.split("#", 2)[0].split(",");
            Controle c = new Controle(vp[0], vp[1], p[2].trim().isEmpty() ? "Controle" : p[2].trim(), p[3].trim());
            if (vistos.add(c.chave())) l.add(c);
        }
        return l;
    }

    public static String limparNome(String n) {
        String s = n.replace(',', ' ').replace('#', ' ').trim().replaceAll("\\s+", " ");
        if (s.length() > 40) s = s.substring(0, 40);
        return s.isEmpty() ? "Controle" : s;
    }

    /** Acrescenta controles novos. Devolve {adicionados, já existiam, sem espaço}. */
    public static int[] registrar(Ftp ftp, List<Controle> novos) throws IOException {
        String t = ftp.lerTextoOuVazio(DEVICES);
        java.nio.charset.Charset cod = ftp.codUltimo;
        Set<String> ja = new HashSet<String>();
        for (Controle c : registrados(t)) ja.add(c.chave());
        int add = 0, existiam = 0, sem = 0, livres = LIMITE_DEVICES - ja.size();
        StringBuilder linhas = new StringBuilder();
        for (Controle c : novos) {
            if (ja.contains(c.chave())) { existiam++; continue; }
            if (livres <= 0) { sem++; continue; }
            linhas.append(String.format(Locale.ROOT, "0x%04x, 0x%04x, %s, %s\n", c.vid, c.pid, limparNome(c.nome), c.tipo));
            ja.add(c.chave());
            add++;
            livres--;
        }
        if (t.trim().isEmpty())
            t = "# Add your custom controller VID/PIDs here, one line per device.\n"
                    + "# Format: VID, PID, NAME, XTYPE   ('#' starts a comment anywhere)\n";
        if (add > 0) {
            t = t.replaceAll("\\n+$", "") + "\n# Adicionado pelo PSTudo\n" + linhas;
            ftp.gravarTexto(DEVICES, t, cod);
        }
        return new int[]{add, existiam, sem};
    }

    public static int remover(Ftp ftp, Controle alvo) throws IOException {
        String t = ftp.lerTexto(DEVICES);
        java.nio.charset.Charset cod = ftp.codUltimo;
        StringBuilder sobra = new StringBuilder();
        int tirou = 0;
        for (String l : t.split("(?<=\\n)")) {
            int[] vp = vidPid(l);
            if (vp != null && vp[0] == alvo.vid && vp[1] == alvo.pid) { tirou++; continue; }
            sobra.append(l);
        }
        if (tirou > 0) ftp.gravarTexto(DEVICES, sobra.toString(), cod);
        return tirou;
    }
}
