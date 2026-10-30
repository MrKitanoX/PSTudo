package com.mrkitanox.pstudo;

import java.text.Normalizer;
import java.util.Locale;

/** Caminhos do PS3, pastas protegidas e textos pequenos usados em todo o app. */
public final class Caminhos {
    private Caminhos() { }

    public static final String[] PASTAS_SISTEMA = {"/dev_flash", "/dev_flash2", "/dev_flash3", "/dev_blind"};
    public static final String[] RAIZES = {"/", "/dev_hdd0", "/dev_hdd1", "/dev_usb000", "/dev_usb001", "/dev_bdvd",
            "/app_home", "/host_root"};
    public static final String[] DESTINOS = {"Automático", "/dev_hdd0/GAMES", "/dev_hdd0/PS3ISO", "/dev_hdd0/packages",
            "/dev_hdd0/PS2ISO", "/dev_hdd0/PSXISO", "/dev_usb000/GAMES"};
    public static final String[] EXT_TEXTO = {".txt", ".cfg", ".ini", ".xml", ".json", ".log", ".conf", ".lst",
            ".md", ".yml", ".yaml", ".csv", ".bat"};
    public static final long LIMITE_EDICAO = 1024 * 1024;

    public static String juntar(String a, String b) {
        if (a.equals("") || a.equals("/")) return "/" + b;
        return a.replaceAll("/+$", "") + "/" + b;
    }

    public static String pai(String c) {
        c = c.replaceAll("/+$", "");
        int i = c.lastIndexOf('/');
        return i <= 0 ? "/" : c.substring(0, i);
    }

    public static String nome(String c) {
        c = c.replaceAll("/+$", "");
        return c.substring(c.lastIndexOf('/') + 1);
    }

    private static boolean dentro(String c, String[] lista) {
        for (String s : lista) if (c.equals(s) || c.startsWith(s + "/")) return true;
        return false;
    }

    public static boolean protegido(String c) {
        String x = c.replaceAll("/+$", "");
        if (x.isEmpty()) x = "/";
        for (String r : RAIZES) if (x.equals(r)) return true;
        return dentro(x, PASTAS_SISTEMA);
    }

    public static boolean sistema(String c) { return dentro(c, PASTAS_SISTEMA); }

    /** Pastas que a pesquisa nas subpastas pula (sistema e cópias de outras pastas). */
    public static boolean foraDaBusca(String c) {
        return dentro(c, PASTAS_SISTEMA) || dentro(c, new String[]{"/dev_bdvd", "/app_home", "/host_root"});
    }

    public static boolean ehTexto(String nome) {
        String n = nome.toLowerCase(Locale.ROOT);
        for (String e : EXT_TEXTO) if (n.endsWith(e)) return true;
        return false;
    }

    /** Destino automático pela extensão (igual ao app do PC). */
    public static String destinoAuto(String nome, boolean pasta, String escolha) {
        if (escolha != null && !escolha.equals("Automático")) return escolha;
        if (pasta) return "/dev_hdd0/GAMES";
        String n = nome.toLowerCase(Locale.ROOT);
        if (n.endsWith(".iso")) return "/dev_hdd0/PS3ISO";
        if (n.endsWith(".pkg")) return "/dev_hdd0/packages";
        if (n.endsWith(".bin") || n.endsWith(".cue")) return "/dev_hdd0/PSXISO";
        return "/dev_hdd0/GAMES";
    }

    public static String semAcento(String s) {
        String n = Normalizer.normalize(s.toLowerCase(Locale.ROOT), Normalizer.Form.NFD);
        return n.replaceAll("\\p{M}", "");
    }

    public static String tamanho(long b) {
        String[] u = {"B", "KB", "MB", "GB", "TB"};
        double v = b;
        int i = 0;
        while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
        String s = i == 0 ? String.valueOf((long) v) : String.format(Locale.ROOT, "%.1f", v).replace('.', ',');
        return s + " " + u[i];
    }

    public static String restante(double seg) {
        if (seg < 60) return L.t("menos de 1 min");
        long m = Math.round(seg / 60);
        if (m < 60) return L.tm("cerca de {0} min", m);
        return L.tm("cerca de {0} h {1} min", m / 60, m % 60);
    }
}
