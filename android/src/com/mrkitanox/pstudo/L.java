package com.mrkitanox.pstudo;

import android.content.Context;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Idiomas do app. As frases estão em português no código; a tradução acontece na hora de mostrar.
 * Frases montadas com números e nomes usam modelos com {0}, {1}… (assets/idiomas/en.json e es.json,
 * os mesmos arquivos da versão do PC).
 */
public final class L {
    public static final String[] CODIGOS = {"pt", "en", "es"};
    public static final String[] NOMES = {"Português", "English", "Español"};
    static String atual = "pt";
    private static final Map<String, String> exato = new HashMap<String, String>();
    private static final Map<String, String> crus = new HashMap<String, String>();
    private static final List<Object[]> modelos = new ArrayList<Object[]>();     // {Pattern, alvo, tamanho}
    private static final Map<String, String> cache = new HashMap<String, String>();
    private static final Pattern ESPACO = Pattern.compile("\\{(\\d+)(?::[^}]*)?\\}");

    private L() { }

    public static String atual() { return atual; }

    /** Troca o idioma (pt = sem tradução). */
    public static synchronized void aplicar(Context c, String cod) {
        exato.clear(); crus.clear(); modelos.clear(); cache.clear();
        atual = "pt";
        if (cod == null || cod.equals("pt")) return;
        try {
            InputStream in = c.getAssets().open("idiomas/" + cod + ".json");
            ByteArrayOutputStream b = new ByteArrayOutputStream();
            byte[] buf = new byte[16384];
            int n;
            while ((n = in.read(buf)) > 0) b.write(buf, 0, n);
            in.close();
            JSONObject o = new JSONObject(new String(b.toByteArray(), "UTF-8"));
            for (Iterator<String> it = o.keys(); it.hasNext(); ) {
                String pt = it.next(), tr = o.getString(pt);
                if (ESPACO.matcher(pt).find()) {
                    crus.put(pt, tr);
                    StringBuilder rx = new StringBuilder("^");
                    Matcher m = ESPACO.matcher(pt);
                    int pos = 0;
                    while (m.find()) {
                        rx.append(Pattern.quote(pt.substring(pos, m.start()).replace("{{", "{").replace("}}", "}")));
                        rx.append("(.+?)");
                        pos = m.end();
                    }
                    rx.append(Pattern.quote(pt.substring(pos).replace("{{", "{").replace("}}", "}"))).append("$");
                    String literal = ESPACO.matcher(pt).replaceAll("");
                    int letras = 0;
                    for (int i = 0; i < literal.length(); i++) if (Character.isLetter(literal.charAt(i))) letras++;
                    if (letras >= 3) modelos.add(new Object[]{Pattern.compile(rx.toString(), Pattern.DOTALL), tr, literal.length()});
                } else {
                    exato.put(pt, tr);
                }
            }
            Collections.sort(modelos, new Comparator<Object[]>() {
                public int compare(Object[] a, Object[] b) { return (Integer) b[2] - (Integer) a[2]; }
            });
            atual = cod;
        } catch (Exception e) {
            exato.clear(); crus.clear(); modelos.clear();
            atual = "pt";
        }
    }

    private static String preencher(String alvo, List<String> grupos) {
        Matcher m = ESPACO.matcher(alvo);
        StringBuffer sb = new StringBuffer();
        while (m.find()) {
            int i = Integer.parseInt(m.group(1));
            m.appendReplacement(sb, Matcher.quoteReplacement(i < grupos.size() ? grupos.get(i) : ""));
        }
        m.appendTail(sb);
        return sb.toString().replace("{{", "{").replace("}}", "}");
    }

    /** Traduz uma frase da interface (devolve igual se não souber). */
    public static synchronized String t(String s) {
        if (atual.equals("pt") || s == null || s.trim().isEmpty()) return s;
        String r = cache.get(s);
        if (r != null) return r;
        r = exato.get(s);
        if (r == null) {
            String nu = s.trim();
            if (!nu.equals(s) && exato.containsKey(nu)) r = s.replace(nu, exato.get(nu));
            else {
                for (Object[] mo : modelos) {
                    Matcher m = ((Pattern) mo[0]).matcher(s);
                    if (m.matches()) {
                        List<String> g = new ArrayList<String>();
                        for (int i = 1; i <= m.groupCount(); i++) g.add(t(m.group(i)));
                        r = preencher((String) mo[1], g);
                        break;
                    }
                }
            }
            if (r == null && s.indexOf('\n') >= 0) {
                String[] linhas = s.split("\n", -1);
                StringBuilder sb = new StringBuilder();
                boolean mudou = false;
                for (int i = 0; i < linhas.length; i++) {
                    String x = t(linhas[i]);
                    if (!x.equals(linhas[i])) mudou = true;
                    if (i > 0) sb.append('\n');
                    sb.append(x);
                }
                if (mudou) r = sb.toString();
            }
            if (r == null) r = s;
        }
        if (cache.size() > 3000) cache.clear();
        cache.put(s, r);
        return r;
    }

    public static CharSequence t(CharSequence s) { return s instanceof String ? t((String) s) : s; }

    /** Modelo com {0}, {1}… montado já no idioma escolhido. */
    public static synchronized String tm(String modelo, Object... v) {
        String alvo = atual.equals("pt") ? null : crus.get(modelo);
        List<String> g = new ArrayList<String>();
        for (Object o : v) g.add(String.valueOf(o));
        return preencher(alvo != null ? alvo : modelo, g);
    }

    /** String.format com o texto traduzido (%d, %s…). */
    public static String f(String fmt, Object... v) { return String.format(Locale.ROOT, t(fmt), v); }

    public static String formatoData() { return "en".equals(atual) ? "MM/dd/yyyy" : "dd/MM/yyyy"; }
}
