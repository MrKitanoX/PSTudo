package com.mrkitanox.pstudo;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.Charset;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Cliente FTP pequeno, feito para o servidor do webMAN MOD.
 * O canal de comandos usa latin-1: o webMAN manda bytes fora do UTF-8 (ex.: "°C" nas respostas),
 * e os nomes de arquivo vão como bytes UTF-8 (convertidos por {@link #paraFtp}).
 */
public class Ftp {
    public static final Charset LATIN1 = Charset.forName("ISO-8859-1");
    public static final Charset UTF8 = Charset.forName("UTF-8");
    public static final int BLOCO = 256 * 1024;

    public static class Erro extends IOException {
        public final int codigo;
        public Erro(int codigo, String msg) { super(msg); this.codigo = codigo; }
    }

    public static class Item {
        public final String nome;      // forma do FTP (latin-1)
        public final boolean pasta;
        public final long tamanho;
        public Item(String nome, boolean pasta, long tamanho) { this.nome = nome; this.pasta = pasta; this.tamanho = tamanho; }
    }

    public interface Progresso { void bytes(long n) throws IOException; }

    private Socket sock;
    private InputStream in;
    private OutputStream out;
    private final String host;
    private final int porta;
    private boolean binario = false;

    public Ftp(String host, int porta) { this.host = host; this.porta = porta; }

    /** Nome vindo do celular (Java/UTF-16) -> forma usada na conexão (bytes UTF-8 lidos como latin-1). */
    public static String paraFtp(String s) { return new String(s.getBytes(UTF8), LATIN1); }

    /** Nome vindo do PS3 -> texto bonito (se for UTF-8 válido). */
    public static String legivel(String s) {
        byte[] b = s.getBytes(LATIN1);
        java.nio.charset.CharsetDecoder d = UTF8.newDecoder();
        try {
            return d.decode(java.nio.ByteBuffer.wrap(b)).toString();
        } catch (java.nio.charset.CharacterCodingException e) {
            return s;
        }
    }

    public void conectar(String usuario, String senha) throws IOException {
        sock = new Socket();
        sock.connect(new InetSocketAddress(host, porta), 8000);
        sock.setSoTimeout(30000);
        in = sock.getInputStream();
        out = sock.getOutputStream();
        resposta(220);
        int c = cmd("USER " + (usuario == null || usuario.isEmpty() ? "anonymous" : usuario));
        if (c == 331) esperar(cmd("PASS " + (senha == null ? "" : senha)), 230, 202);
        else esperar(c, 230, 202);
    }

    public void fechar() {
        try { if (sock != null && !sock.isClosed()) { enviar("QUIT"); resposta(); } } catch (Exception ignored) { }
        try { if (sock != null) sock.close(); } catch (Exception ignored) { }
    }

    // ---------------------------------------------------------------- comandos
    private String ultima = "";

    private void enviar(String linha) throws IOException {
        out.write((linha + "\r\n").getBytes(LATIN1));
        out.flush();
    }

    private String linha() throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        int ch;
        while ((ch = in.read()) != -1) {
            if (ch == '\n') break;
            if (ch != '\r') b.write(ch);
        }
        if (ch == -1 && b.size() == 0) throw new IOException("O PS3 fechou a conexão");
        return new String(b.toByteArray(), LATIN1);
    }

    /** Lê uma resposta completa (inclusive as de várias linhas) e devolve o código. */
    private int resposta() throws IOException {
        String l = linha();
        while (l.length() < 3 || !Character.isDigit(l.charAt(0))) l = linha();
        String cod = l.substring(0, 3);
        if (l.length() > 3 && l.charAt(3) == '-') {
            String fim = cod + " ";
            String x;
            do { x = linha(); } while (!x.startsWith(fim));
            l = x;
        }
        ultima = l;
        return Integer.parseInt(cod);
    }

    private void resposta(int... ok) throws IOException { esperar(resposta(), ok); }

    private void esperar(int c, int... ok) throws Erro {
        for (int o : ok) if (c == o) return;
        throw new Erro(c, ultima);
    }

    public int cmd(String c) throws IOException { enviar(c); return resposta(); }

    public String ultimaResposta() { return ultima; }

    private void tipoBinario() throws IOException {
        if (!binario) { esperar(cmd("TYPE I"), 200); binario = true; }
    }

    private Socket pasv() throws IOException {
        esperar(cmd("PASV"), 227);
        Matcher m = Pattern.compile("(\\d+),(\\d+),(\\d+),(\\d+),(\\d+),(\\d+)").matcher(ultima);
        if (!m.find()) throw new Erro(227, "Resposta PASV estranha: " + ultima);
        int p = Integer.parseInt(m.group(5)) * 256 + Integer.parseInt(m.group(6));
        Socket d = new Socket();
        d.connect(new InetSocketAddress(host, p), 8000);   // usa o IP do PS3, não o da resposta
        d.setSoTimeout(60000);
        return d;
    }

    // ---------------------------------------------------------------- operações
    public List<Item> listar(String caminho) throws IOException {
        List<Item> itens = new ArrayList<Item>();
        boolean mlsd = true;
        tipoBinario();
        Socket d = pasv();
        int c = cmd("MLSD " + caminho);
        if (c != 150 && c != 125) {
            d.close();
            mlsd = false;
            binario = false;
            esperar(cmd("TYPE A"), 200);
            d = pasv();
            c = cmd("LIST " + caminho);
            if (c != 150 && c != 125) { d.close(); throw new Erro(c, ultima); }
        }
        BufferedReader r = new BufferedReader(new InputStreamReader(d.getInputStream(), LATIN1));
        String l;
        while ((l = r.readLine()) != null) {
            if (l.trim().isEmpty()) continue;
            if (mlsd) {
                int sp = l.indexOf(' ');
                if (sp < 0) continue;
                String fatos = l.substring(0, sp).toLowerCase(), nome = l.substring(sp + 1);
                if (nome.equals(".") || nome.equals("..")) continue;
                String tipo = fato(fatos, "type");
                if ("cdir".equals(tipo) || "pdir".equals(tipo)) continue;
                long tam = 0;
                try { tam = Long.parseLong(fato(fatos, "size")); } catch (Exception ignored) { }
                itens.add(new Item(nome, "dir".equals(tipo), tam));
            } else {
                String[] p = l.trim().split("\\s+", 9);
                if (p.length < 9 || p[8].equals(".") || p[8].equals("..")) continue;
                long tam = 0;
                try { tam = Long.parseLong(p[4]); } catch (Exception ignored) { }
                itens.add(new Item(p[8], l.startsWith("d"), tam));
            }
        }
        r.close();
        d.close();
        resposta(226, 250);
        if (!mlsd) { binario = false; }
        ordenar(itens);
        return itens;
    }

    private static String fato(String fatos, String chave) {
        for (String f : fatos.split(";")) {
            int i = f.indexOf('=');
            if (i > 0 && f.substring(0, i).equals(chave)) return f.substring(i + 1);
        }
        return null;
    }

    /** Pastas primeiro, depois ordem natural (Jogo_2 antes de Jogo_10). */
    public static void ordenar(List<Item> itens) {
        Collections.sort(itens, new Comparator<Item>() {
            public int compare(Item a, Item b) {
                if (a.pasta != b.pasta) return a.pasta ? -1 : 1;
                return natural(a.nome, b.nome);
            }
        });
    }

    public static int natural(String a, String b) {
        Matcher ma = Pattern.compile("\\d+|\\D+").matcher(a.toLowerCase());
        Matcher mb = Pattern.compile("\\d+|\\D+").matcher(b.toLowerCase());
        while (ma.find() && mb.find()) {
            String x = ma.group(), y = mb.group();
            int c;
            if (Character.isDigit(x.charAt(0)) && Character.isDigit(y.charAt(0))) {
                c = new java.math.BigInteger(x).compareTo(new java.math.BigInteger(y));
            } else c = x.compareTo(y);
            if (c != 0) return c;
        }
        return a.length() - b.length();
    }

    /** Tamanho do arquivo no PS3, ou -1 se não existir. */
    public long tamanho(String caminho) {
        try {
            tipoBinario();
            int c = cmd("SIZE " + caminho);
            if (c != 213) return -1;
            return Long.parseLong(ultima.substring(4).trim());
        } catch (Exception e) {
            return -1;
        }
    }

    public boolean existe(String caminho) { return tamanho(caminho) >= 0; }

    public void enviar(String remoto, InputStream dados, Progresso prog) throws IOException {
        tipoBinario();
        Socket d = pasv();
        int c = cmd("STOR " + remoto);
        if (c != 150 && c != 125) { d.close(); throw new Erro(c, ultima); }
        OutputStream o = d.getOutputStream();
        byte[] buf = new byte[BLOCO];
        int n;
        try {
            while ((n = dados.read(buf)) > 0) {
                o.write(buf, 0, n);
                if (prog != null) prog.bytes(n);
            }
            o.flush();
        } finally {
            try { o.close(); } catch (IOException ignored) { }
            d.close();
        }
        resposta(226, 250);
    }

    public void enviar(String remoto, byte[] dados) throws IOException {
        enviar(remoto, new java.io.ByteArrayInputStream(dados), null);
    }

    public void baixar(String remoto, OutputStream destino, Progresso prog) throws IOException {
        tipoBinario();
        Socket d = pasv();
        int c = cmd("RETR " + remoto);
        if (c != 150 && c != 125) { d.close(); throw new Erro(c, ultima); }
        InputStream i = d.getInputStream();
        byte[] buf = new byte[BLOCO];
        int n;
        try {
            while ((n = i.read(buf)) > 0) {
                destino.write(buf, 0, n);
                if (prog != null) prog.bytes(n);
            }
        } finally {
            d.close();
        }
        resposta(226, 250);
    }

    /** Lê só um pedaço do arquivo (a partir de 'inicio') e corta a transferência. */
    public byte[] lerPedaco(String remoto, long inicio, int limite) throws IOException {
        tipoBinario();
        Socket d = pasv();
        if (inicio > 0) {
            int r = cmd("REST " + inicio);
            if (r != 350) { d.close(); throw new Erro(r, ultima); }
        }
        int c = cmd("RETR " + remoto);
        if (c != 150 && c != 125) { d.close(); throw new Erro(c, ultima); }
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        try {
            InputStream i = d.getInputStream();
            byte[] buf = new byte[8192];
            int n;
            while (b.size() < limite && (n = i.read(buf, 0, Math.min(buf.length, limite - b.size()))) > 0)
                b.write(buf, 0, n);
        } finally {
            d.close();
        }
        resposta();      // 226, ou 426 quando a transferência foi cortada
        return b.toByteArray();
    }

    /** true = existe, false = o PS3 disse que não existe (550). Erro de conexão vira exceção. */
    public boolean existeOuErro(String caminho) throws IOException {
        tipoBinario();
        int c = cmd("SIZE " + caminho);
        if (c == 213) return true;
        if (c == 550) return false;
        throw new Erro(c, ultima);
    }

    public byte[] baixar(String remoto) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        baixar(remoto, b, null);
        return b.toByteArray();
    }

    public void criarPasta(String caminho) throws IOException {
        int c = cmd("MKD " + caminho);
        if (c != 257 && c != 250 && c != 550 && c != 521) throw new Erro(c, ultima);
    }

    /** Cria as pastas que faltam até o arquivo (cache evita repetir). */
    public void criarPastasDe(String arquivo, java.util.Set<String> cache) throws IOException {
        String[] partes = arquivo.replaceAll("^/+", "").split("/");
        String atual = "";
        for (int i = 0; i < partes.length - 1; i++) {
            atual += "/" + partes[i];
            if (cache.contains(atual)) continue;
            cmd("MKD " + atual);
            cache.add(atual);
        }
    }

    public void apagarArquivo(String caminho) throws IOException { esperar(cmd("DELE " + caminho), 250, 200); }

    public void apagar(String caminho, boolean pasta) throws IOException {
        if (Caminhos.protegido(caminho)) throw new Erro(550, "Pasta do sistema protegida");
        if (pasta) {
            for (Item it : listar(caminho)) apagar(Caminhos.juntar(caminho, it.nome), it.pasta);
            esperar(cmd("RMD " + caminho), 250, 200);
        } else apagarArquivo(caminho);
    }

    public void renomear(String de, String para) throws IOException {
        esperar(cmd("RNFR " + de), 350);
        esperar(cmd("RNTO " + para), 250, 200);
    }

    /** Codificação do último texto lido (para gravar de volta do mesmo jeito). */
    public Charset codUltimo = UTF8;

    public String lerTexto(String caminho) throws IOException {
        byte[] b = baixar(caminho);
        try {
            codUltimo = UTF8;
            return UTF8.newDecoder().decode(java.nio.ByteBuffer.wrap(b)).toString();
        } catch (java.nio.charset.CharacterCodingException e) {
            codUltimo = LATIN1;
            return new String(b, LATIN1);
        }
    }

    /** Lê o texto ou devolve "" se o arquivo não existir. */
    public String lerTextoOuVazio(String caminho) {
        try { return lerTexto(caminho); } catch (IOException e) { codUltimo = UTF8; return ""; }
    }

    public void gravarTexto(String caminho, String texto, Charset cod) throws IOException {
        enviar(caminho, texto.getBytes(cod == null ? UTF8 : cod));
    }
}
