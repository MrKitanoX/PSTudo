package com.mrkitanox.pstudo;

import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Set;

/** Controle remoto: manda o estado do controle para o controle virtual do webMAN (/pad.ps3?hold...).
    Limites do próprio webMAN: o analógico só vai inclinado até o fim (8 direções) e um analógico por vez. */
public class Remoto {
    public static final String[] BOTOES = {"cross", "circle", "square", "triangle", "L1", "R1", "L2", "R2", "L3", "R3",
            "select", "start", "psbtn"};

    public interface Erro { void erro(String msg); }

    private final String ip;
    private final Erro aoErro;
    private final Object trava = new Object();
    private String pendente = null, desejado = null;
    private boolean vivo = true;
    private final Thread t;

    public Remoto(String ip, Erro aoErro) {
        this.ip = ip;
        this.aoErro = aoErro;
        t = new Thread(new Runnable() { public void run() { loop(); } });
        t.start();
    }

    private static void direcoes(StringBuilder sb, float x, float y) {
        if (y < -0.5f) sb.append("up"); else if (y > 0.5f) sb.append("down");
        if (x < -0.5f) sb.append("left"); else if (x > 0.5f) sb.append("right");
    }

    /** Estado -> texto do /pad.ps3. Eixos de -1 a 1 (y positivo = para baixo).
        O direcional vale mais que o analógico, e o esquerdo mais que o direito. */
    public static String comando(Set<String> botoes, Set<String> dpad, float lx, float ly, float rx, float ry) {
        StringBuilder sb = new StringBuilder("hold");
        for (String b : BOTOES) if (botoes.contains(b)) sb.append('_').append(b);
        if (!dpad.isEmpty()) {
            for (String d : new String[]{"up", "down", "left", "right"}) if (dpad.contains(d)) sb.append('_').append(d);
        } else {
            StringBuilder d = new StringBuilder();
            direcoes(d, lx, ly);
            if (d.length() > 0) sb.append("_analogL_").append(d);
            else {
                direcoes(d, rx, ry);
                if (d.length() > 0) sb.append("_analogR_").append(d);
            }
        }
        return sb.toString();
    }

    public void enviar(String cmd) {
        synchronized (trava) {
            if (cmd.equals(desejado)) return;
            desejado = pendente = cmd;
            trava.notifyAll();
        }
    }

    /** Solta tudo e desliga o controle virtual do PS3. */
    public void parar() {
        synchronized (trava) {
            vivo = false;
            trava.notifyAll();
        }
    }

    private int pedir(String caminho) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL("http://" + ip + "/" + caminho).openConnection();
        c.setConnectTimeout(3000);
        c.setReadTimeout(4000);
        c.setUseCaches(false);
        try {
            int cod = c.getResponseCode();
            InputStream in = cod >= 400 ? c.getErrorStream() : c.getInputStream();
            if (in != null) {
                byte[] buf = new byte[4096];
                while (in.read(buf) > 0) { }      // ler tudo deixa a conexão pronta para o próximo pedido
                in.close();
            }
            return cod;
        } finally {
            c.disconnect();
        }
    }

    private void loop() {
        while (true) {
            String cmd;
            synchronized (trava) {
                while (vivo && pendente == null) {
                    try { trava.wait(); } catch (InterruptedException e) { return; }
                }
                if (!vivo) break;
                cmd = pendente;
                pendente = null;
            }
            try {
                int cod = pedir("pad.ps3?" + cmd);
                if (cod == 400 || cod == 404 || cod == 501) {
                    if (aoErro != null) aoErro.erro("O webMAN do seu PS3 não tem o controle virtual. Use a versão completa do webMAN MOD (não a Lite).");
                    break;
                }
            } catch (Exception e) {
                synchronized (trava) { if (pendente == null) pendente = desejado; }   // tenta de novo com o mais recente
                try { Thread.sleep(500); } catch (InterruptedException ie) { return; }
            }
        }
        try { pedir("pad.ps3?hold"); } catch (Exception ignored) { }
        try { pedir("pad.ps3?off"); } catch (Exception ignored) { }
    }
}
