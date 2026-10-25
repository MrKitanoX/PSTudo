package com.mrkitanox.pstudo;

import java.io.InputStream;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.Socket;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Procura o PS3 (servidor FTP do webMAN) nas redes do celular. */
public final class Rede {
    private Rede() { }

    /** Cumprimento do FTP, ou null. Se a porta abrir, espera mais pelo cumprimento (o webMAN às vezes demora). */
    public static String testarFtp(String ip, int porta, int timeoutMs) {
        Socket s = new Socket();
        try {
            s.connect(new InetSocketAddress(ip, porta), timeoutMs);
            s.setSoTimeout(Math.max(3000, timeoutMs * 2));
            InputStream in = s.getInputStream();
            byte[] b = new byte[256];
            int n = in.read(b);
            if (n <= 0) return null;
            String t = new String(b, 0, n, Ftp.LATIN1);
            return t.startsWith("220") ? t : null;
        } catch (Exception e) {
            return null;
        } finally {
            try { s.close(); } catch (Exception ignored) { }
        }
    }

    private static boolean privado(byte[] a) {
        int x = a[0] & 0xff, y = a[1] & 0xff;
        return x == 10 || (x == 172 && y >= 16 && y <= 31) || (x == 192 && y == 168);
    }

    /** IPv4 de rede local deste aparelho (Wi-Fi, cabo, hotspot). */
    public static List<String> ipsLocais() {
        List<String> ips = new ArrayList<String>();
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                String nome = ni.getName().toLowerCase();
                boolean preferida = nome.startsWith("wlan") || nome.startsWith("eth");
                for (InetAddress a : Collections.list(ni.getInetAddresses())) {
                    if (a instanceof Inet4Address && privado(a.getAddress())) {
                        if (preferida) ips.add(0, a.getHostAddress()); else ips.add(a.getHostAddress());
                    }
                }
            }
        } catch (Exception ignored) { }
        return ips;
    }

    public static String procurar(int porta, String salvo) {
        if (salvo != null && !salvo.isEmpty() && testarFtp(salvo, porta, 1500) != null) return salvo;
        final List<String> meus = ipsLocais();
        List<String> candidatos = new ArrayList<String>();
        for (String meu : meus) {
            String base = meu.substring(0, meu.lastIndexOf('.'));
            for (int i = 1; i < 255; i++) {
                String c = base + "." + i;
                if (!meus.contains(c) && !candidatos.contains(c)) candidatos.add(c);
            }
        }
        if (candidatos.isEmpty()) return null;
        final AtomicReference<String> achou = new AtomicReference<String>();
        final List<String> outros = Collections.synchronizedList(new ArrayList<String>());
        final int p = porta;
        ExecutorService ex = Executors.newFixedThreadPool(64);
        for (final String ip : candidatos) {
            ex.submit(new Runnable() {
                public void run() {
                    if (achou.get() != null) return;
                    String b = testarFtp(ip, p, 1000);
                    if (b == null) return;
                    String l = b.toLowerCase();
                    if (l.contains("webman") || l.contains("multiman") || l.contains("ps3")) achou.compareAndSet(null, ip);
                    else outros.add(ip);
                }
            });
        }
        ex.shutdown();
        try {
            long fim = System.currentTimeMillis() + 30000;
            while (!ex.isTerminated() && achou.get() == null && System.currentTimeMillis() < fim)
                ex.awaitTermination(200, TimeUnit.MILLISECONDS);
        } catch (InterruptedException ignored) { }
        ex.shutdownNow();
        if (achou.get() != null) return achou.get();
        return outros.isEmpty() ? null : outros.get(0);
    }
}
