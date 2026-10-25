package com.mrkitanox.pstudo;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.net.URLEncoder;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Comandos web do webMAN MOD (porta 80 do PS3). */
public final class WebMan {
    private WebMan() { }

    public static class ErroHttp extends IOException {
        public final int codigo;
        public ErroHttp(int c) { super("HTTP " + c); codigo = c; }
    }

    public static String http(String ip, String caminho, int timeoutMs) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL("http://" + ip + "/" + caminho).openConnection();
        c.setConnectTimeout(Math.min(timeoutMs, 8000));
        c.setReadTimeout(timeoutMs);
        c.setUseCaches(false);
        try {
            int cod = c.getResponseCode();
            if (cod >= 400) throw new ErroHttp(cod);
            InputStream in = c.getInputStream();
            ByteArrayOutputStream b = new ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int n;
            while (b.size() < 65536 && (n = in.read(buf)) > 0) b.write(buf, 0, n);
            in.close();
            return new String(b.toByteArray(), Ftp.LATIN1);
        } finally {
            c.disconnect();
        }
    }

    /** Pedido que pode derrubar a conexão (reiniciar, recarregar XMB): queda conta como sucesso. */
    private static void pedirTolerante(String ip, String caminho, int timeoutMs) throws IOException {
        try {
            http(ip, caminho, timeoutMs);
        } catch (ErroHttp e) {
            throw e;
        } catch (SocketTimeoutException e) {
            // o comando chegou; o PS3 só não respondeu a tempo
        } catch (IOException e) {
            String m = String.valueOf(e.getMessage()).toLowerCase();
            if (!(m.contains("reset") || m.contains("end of stream") || m.contains("unexpected end")
                    || m.contains("closed") || m.contains("eof"))) throw e;
        }
    }

    public static String url(String s) {
        try {
            return URLEncoder.encode(s, "UTF-8").replace("+", "%20").replace("%2F", "/");
        } catch (Exception e) {
            return s;
        }
    }

    public static void energia(String ip, boolean reiniciar) throws IOException {
        pedirTolerante(ip, reiniciar ? "restart.ps3" : "shutdown.ps3", 6000);
    }

    public static void popup(String ip, String texto) {
        try { http(ip, "popup.ps3/" + url(texto), 3000); } catch (Exception ignored) { }
    }

    /** Atualiza a lista de jogos e recarrega o XMB. false = o webMAN não sabe recarregar o XMB. */
    public static boolean atualizarXmb(String ip) throws IOException {
        pedirTolerante(ip, "refresh.ps3", 120000);
        try {
            pedirTolerante(ip, "reloadxmb.ps3", 20000);
        } catch (ErroHttp e) {
            if (e.codigo == 400 || e.codigo == 404 || e.codigo == 501) return false;
            throw e;
        }
        return true;
    }

    // ---------------------------------------------------------------- plugins (só nesta sessão)
    /** {caminho: slot} do que está carregado, ou null se o PS3 não informar. */
    public static Map<String, Integer> pluginsAtivos(String ip) {
        Map<String, Integer> ativos = new LinkedHashMap<String, Integer>();
        boolean respondeu = false;
        Pattern p = Pattern.compile("(/dev_[^\"'<>\\s,]+?\\.sprx)", Pattern.CASE_INSENSITIVE);
        for (int slot = 0; slot < 7; slot++) {
            try {
                String t = http(ip, "ps3mapi.ps3?MODULE%20GETVSHPLUGINFO%20" + slot, 4000);
                respondeu = true;
                Matcher m = p.matcher(t);
                if (m.find()) ativos.put(m.group(1), slot);
            } catch (IOException ignored) { }
        }
        return respondeu ? ativos : null;
    }

    private static Boolean esperarPlugin(String ip, String caminho, int segundos) {
        long fim = System.currentTimeMillis() + segundos * 1000L;
        boolean respondeu = false;
        while (System.currentTimeMillis() < fim) {
            Map<String, Integer> a = pluginsAtivos(ip);
            if (a != null) {
                respondeu = true;
                if (a.containsKey(caminho)) return true;
            }
            try { Thread.sleep(2000); } catch (InterruptedException e) { break; }
        }
        return respondeu ? Boolean.FALSE : null;
    }

    /** Carrega o plugin só até reiniciar. Usa /loadprx.ps3 (todas as versões) e o PS3MAPI como plano B. */
    public static int ativar(String ip, String caminho, Map<String, Integer> ocupados) throws IOException {
        int slot = 6;
        if (ocupados != null) {
            slot = -1;
            for (int s = 6; s >= 1; s--) if (!ocupados.containsValue(s)) { slot = s; break; }
            if (slot < 0) throw new IOException("Todos os espaços de plugin do PS3 estão ocupados. Desative algum antes.");
        }
        String prx = url(caminho);
        try {
            http(ip, "loadprx.ps3?slot=" + slot + "&prx=" + prx, 20000);
        } catch (SocketTimeoutException e) {
            // o webMAN só responde quando o plugin termina de iniciar (o XPAD demora)
            if (Boolean.FALSE.equals(esperarPlugin(ip, caminho, 25)))
                throw new IOException("O PS3 não respondeu a tempo e o plugin não apareceu como ativo.");
        } catch (ErroHttp e) {
            if (e.codigo != 400 && e.codigo != 404 && e.codigo != 501) throw e;
            try {
                http(ip, "vshplugin.ps3mapi?load_slot=" + slot + "&prx=" + prx, 20000);
            } catch (ErroHttp e2) {
                throw new IOException("O webMAN MOD do seu PS3 não aceitou o comando para carregar plugins. "
                        + "Atualize o webMAN MOD.");
            }
        }
        return slot;
    }

    /** Tira o plugin da memória. Alguns (como o XPAD) demoram para sair e o webMAN só responde depois,
        ou nem responde: o pedido conta como enviado e aqui se confere se ele saiu mesmo. */
    public static void desativar(String ip, String caminho, Integer slot) throws IOException {
        try {
            if (slot != null) pedirTolerante(ip, "unloadprx.ps3?slot=" + slot, 10000);
            else pedirTolerante(ip, "unloadprx.ps3" + url(caminho), 10000);
        } catch (ErroHttp e) {
            if (slot == null || (e.codigo != 400 && e.codigo != 404 && e.codigo != 501)) throw e;
            pedirTolerante(ip, "vshplugin.ps3mapi?unload_slot=" + slot, 10000);
        }
        long fim = System.currentTimeMillis() + 15000;
        Map<String, Integer> at = null;
        while (System.currentTimeMillis() < fim) {
            at = pluginsAtivos(ip);
            if (at != null && !at.containsKey(caminho)) return;
            try { Thread.sleep(1500); } catch (InterruptedException e) { break; }
        }
        if (at != null && at.containsKey(caminho))
            throw new IOException("o PS3 não tirou o plugin da memória. Reinicie o PS3 para desligá-lo de vez.");
    }
}
