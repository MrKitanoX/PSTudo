package com.mrkitanox.pstudo;

import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.CheckBox;
import android.widget.CompoundButton;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.Date;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Aba Troféus: ver e destravar localmente os troféus dos jogos do PS3 (com backup e "Desfazer"). */
public class TabTrofeus {
    static final int ABA = 6;
    static final String HOME = "/dev_hdd0/home";
    static final String[] MUDAM = {"TROPUSR.DAT", "TROPTRNS.DAT", "PARAM.PFD"};

    static class Jogo { String pasta, codigo, nome, erro = ""; int total, ganhos; }

    private final MainActivity a;
    private List<String[]> usuarios = null;      // {id, nome}
    private String usuario = null;
    private List<Jogo> jogos = null;
    private boolean lendo = false, ocupado = false;
    private String sel = null;
    private final Map<String, Object> listas = new HashMap<String, Object>();   // List<Trofeu> ou IOException
    private final Set<Integer> marcados = new HashSet<Integer>();
    private String msg = "";
    private int msgCor = Ui.CINZA;
    private TextView lblMsg;

    TabTrofeus(MainActivity a) { this.a = a; }

    private int dp(float v) { return a.dp(v); }

    void statusMudou() {
        if (a.abaAtual() != ABA) return;
        if (a.conectado() && jogos == null && !lendo) ler();
        else redesenhar();
    }

    private void msg(String t, int cor) {
        msg = t; msgCor = cor;
        if (lblMsg != null) { lblMsg.setText(t); lblMsg.setTextColor(cor); }
    }

    private void redesenhar() { if (a.abaAtual() == ABA) a.mostrarAba(ABA); }

    View view() {
        lblMsg = null;
        View v = sel == null ? telaJogos() : telaTrofeus();
        if (sel == null && jogos == null && !lendo && a.conectado())
            a.h.post(new Runnable() { public void run() { ler(); } });
        return v;
    }

    private LinearLayout base() {
        LinearLayout c = Ui.coluna(a);
        c.setPadding(dp(14), dp(6), dp(14), dp(10));
        return c;
    }

    private void rodape(LinearLayout c) {
        lblMsg = Ui.texto(a, msg, 12, msgCor, Ui.NORMAL);
        c.addView(lblMsg, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 2, 6, 2, 6));
    }

    private void aviso(LinearLayout l, String t, int cor) {
        TextView tv = Ui.texto(a, t, 13, cor, Ui.NORMAL);
        tv.setGravity(Gravity.CENTER);
        tv.setPadding(0, dp(30), 0, dp(16));
        l.addView(tv, Ui.lp(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
    }

    private View telaJogos() {
        LinearLayout c = base();
        LinearLayout topo = Ui.linha(a);
        topo.addView(Ui.texto(a, "Troféus", 22, Ui.BRANCO, Ui.LEVE), Ui.lpPeso(1));
        TextView ler = Ui.botao(a, "⟳ Ler", "contorno", new View.OnClickListener() { public void onClick(View v) { ler(); } });
        ler.setTextSize(12);
        ler.setMinHeight(dp(34));
        ler.setPadding(dp(12), dp(4), dp(12), dp(4));
        Ui.ativo(ler, a.conectado() && !lendo && !ocupado);
        topo.addView(ler);
        c.addView(topo);
        if (usuarios != null && usuarios.size() > 1) {
            LinearLayout us = Ui.linha(a);
            for (final String[] u : usuarios) {
                TextView b = Ui.botao(a, u[1], u[0].equals(usuario) ? "azul" : "contorno", new View.OnClickListener() {
                    public void onClick(View v) {
                        if (u[0].equals(usuario) || lendo) return;
                        usuario = u[0]; jogos = null; listas.clear(); marcados.clear();
                        ler();
                    }
                });
                b.setTextSize(12);
                b.setMinHeight(dp(34));
                us.addView(b, Ui.margem(a, ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 0, 6, 0));
            }
            c.addView(us, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 6, 0, 0));
        }
        ScrollView sv = new ScrollView(a);
        LinearLayout lista = Ui.coluna(a);
        if (jogos == null) aviso(lista, lendo ? "Lendo os troféus do PS3…" : a.conectado() ? "" : "Conecte o PS3 para ver os troféus.", Ui.CINZA);
        else if (jogos.isEmpty()) aviso(lista, "Nenhum jogo com troféus neste usuário.", Ui.CINZA);
        else for (final Jogo j : jogos) {
            LinearLayout l = Ui.coluna(a);
            l.setBackground(Ui.estados(a, Ui.CARD, Ui.LINHA_SEL, 12, 0));
            l.setPadding(dp(14), dp(10), dp(14), dp(10));
            TextView n = Ui.texto(a, j.nome, 14, Ui.BRANCO, Ui.FORTE);
            n.setSingleLine(true);
            n.setEllipsize(android.text.TextUtils.TruncateAt.END);
            l.addView(n);
            int pct = j.total > 0 ? j.ganhos * 100 / j.total : 0;
            l.addView(Ui.texto(a, j.erro.isEmpty() ? j.ganhos + " de " + j.total + " troféus  •  " + pct + "%"
                    : "Não consegui ler: " + j.erro, 12, j.erro.isEmpty() ? Ui.CINZA_ESCURO : Ui.VERMELHO, Ui.NORMAL));
            l.setClickable(true);
            l.setOnClickListener(new View.OnClickListener() { public void onClick(View v) { escolher(j.codigo, false); } });
            lista.addView(l, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 0, 0, 6));
        }
        sv.addView(lista);
        c.addView(sv, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, 0, 0, 10, 0, 0));
        ((LinearLayout.LayoutParams) sv.getLayoutParams()).weight = 1;
        rodape(c);
        return c;
    }

    private Jogo jogo(String cod) {
        if (jogos != null) for (Jogo j : jogos) if (j.codigo.equals(cod)) return j;
        return null;
    }

    private View telaTrofeus() {
        LinearLayout c = base();
        final Jogo j = jogo(sel);
        LinearLayout topo = Ui.linha(a);
        TextView voltar = Ui.botao(a, "←", "normal", new View.OnClickListener() {
            public void onClick(View v) { if (ocupado) return; sel = null; marcados.clear(); msg("", Ui.CINZA); redesenhar(); }
        });
        voltar.setPadding(dp(14), dp(4), dp(14), dp(4));
        topo.addView(voltar, Ui.margem(a, ViewGroup.LayoutParams.WRAP_CONTENT, dp(40), 0, 0, 10, 0));
        LinearLayout tt = Ui.coluna(a);
        TextView tn = Ui.texto(a, j != null ? j.nome : sel, 17, Ui.BRANCO, Ui.FORTE);
        tn.setMaxLines(2);
        tt.addView(tn);
        tt.addView(Ui.texto(a, sel + (j != null ? "  •  " + j.ganhos + " de " + j.total : ""), 12, Ui.CINZA, Ui.NORMAL));
        topo.addView(tt, Ui.lpPeso(1));
        c.addView(topo, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 4, 0, 8));

        ScrollView sv = new ScrollView(a);
        LinearLayout lista = Ui.coluna(a);
        Object o = listas.get(sel);
        List<Trofeus.Trofeu> trofeus = null;
        if (o == null) aviso(lista, "Lendo os troféus…", Ui.CINZA);
        else if (o instanceof IOException) aviso(lista, "Não consegui ler estes troféus.\n(" + ((IOException) o).getMessage() + ")", Ui.VERMELHO);
        else {
            @SuppressWarnings("unchecked") List<Trofeus.Trofeu> x = (List<Trofeus.Trofeu>) o;
            trofeus = x;
            int[] cores = {Ui.CINZA, 0xFF7FD3F7, 0xFFF5C542, 0xFFC9D1DC, 0xFFD08A55};
            for (final Trofeus.Trofeu t : trofeus) {
                LinearLayout l = Ui.linha(a);
                l.setBackground(Ui.fundo(a, Ui.CARD, 12, 0));
                l.setPadding(dp(8), dp(8), dp(12), dp(8));
                if (t.destravado) {
                    TextView ok = Ui.texto(a, "✓", 16, Ui.VERDE, Ui.FORTE);
                    ok.setGravity(Gravity.CENTER);
                    l.addView(ok, Ui.lp(dp(40), ViewGroup.LayoutParams.WRAP_CONTENT));
                } else {
                    CheckBox cb = new CheckBox(a);
                    cb.setChecked(marcados.contains(t.id));
                    cb.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
                        public void onCheckedChanged(CompoundButton b, boolean on) {
                            if (on) marcados.add(t.id); else marcados.remove(t.id);
                            atualizarBotoes();
                        }
                    });
                    l.addView(cb, Ui.lp(dp(40), ViewGroup.LayoutParams.WRAP_CONTENT));
                }
                LinearLayout col = Ui.coluna(a);
                int tp = t.tipo >= 1 && t.tipo <= 4 ? t.tipo : 0;
                TextView nm = Ui.texto(a, "● " + t.nome + (t.oculto ? "  (oculto)" : ""), 14, Ui.BRANCO, Ui.FORTE);
                android.text.SpannableString sp = new android.text.SpannableString(nm.getText());
                sp.setSpan(new android.text.style.ForegroundColorSpan(cores[tp]), 0, 1, 0);
                nm.setText(sp);
                col.addView(nm);
                String det = Trofeus.TIPOS[tp] + (t.detalhe.isEmpty() ? "" : "  •  " + t.detalhe);
                col.addView(Ui.texto(a, det, 12, Ui.CINZA, Ui.NORMAL));
                if (t.destravado) {
                    String q = t.tempo != 0 ? new SimpleDateFormat("dd/MM/yyyy", Locale.ROOT).format(new Date(Trofeus.tempoMs(t.tempo))) : "";
                    col.addView(Ui.texto(a, (t.sync ? "na PSN" : "ganho") + (q.isEmpty() ? "" : "  •  " + q), 11,
                            t.sync ? Ui.VERDE : 0xFF7FB2F0, Ui.NORMAL));
                }
                l.addView(col, Ui.lpPeso(1));
                lista.addView(l, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 0, 0, 6));
            }
        }
        sv.addView(lista);
        c.addView(sv, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        rodape(c);
        LinearLayout b1 = Ui.linha(a);
        bDesfazer = Ui.botao(a, "Desfazer", "contorno", new View.OnClickListener() { public void onClick(View v) { desfazer(); } });
        b1.addView(bDesfazer, Ui.lpPeso(1));
        b1.addView(Ui.espaco(a, 1), Ui.lp(dp(8), 1));
        final List<Trofeus.Trofeu> tf = trofeus;
        bTodos = Ui.botao(a, "Marcar os que faltam", "contorno", new View.OnClickListener() {
            public void onClick(View v) {
                if (tf == null) return;
                marcados.clear();
                for (Trofeus.Trofeu t : tf) if (!t.destravado) marcados.add(t.id);
                redesenhar();
            }
        });
        b1.addView(bTodos, Ui.lpPeso(1.4f));
        c.addView(b1, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 0, 0, 8));
        bDestravar = Ui.botao(a, "Destravar", "azul", new View.OnClickListener() { public void onClick(View v) { destravar(); } });
        bDestravar.setMinHeight(dp(50));
        c.addView(bDestravar, Ui.lp(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        atualizarBotoes();
        return c;
    }

    private TextView bDesfazer, bTodos, bDestravar;

    private void atualizarBotoes() {
        if (bDestravar == null) return;
        boolean livre = !ocupado && a.conectado();
        Object o = listas.get(sel);
        boolean faltam = false;
        if (o instanceof List) for (Object t : (List<?>) o) if (!((Trofeus.Trofeu) t).destravado) faltam = true;
        bDestravar.setText(marcados.isEmpty() ? "Destravar" : "Destravar " + marcados.size());
        Ui.ativo(bDestravar, livre && !marcados.isEmpty());
        Ui.ativo(bTodos, livre && faltam);
        Ui.ativo(bDesfazer, livre && ultimoBackup() != null);
    }

    // ------------------------------------------------------------------ backups (no celular)
    private File pastaBackup() {
        File b = a.getExternalFilesDir(null);
        if (b == null) b = a.getFilesDir();
        return new File(b, "backup_trofeus/" + usuario + "/" + sel);
    }

    private File ultimoBackup() {
        if (usuario == null || sel == null) return null;
        File[] l = pastaBackup().listFiles();
        if (l == null) return null;
        List<File> ok = new ArrayList<File>();
        for (File f : l)      // só o que o PSTudo gravou de fato (tem a pasta "depois")
            if (f.isDirectory() && !f.getName().endsWith("_desfeito") && new File(f, "depois").isDirectory()) ok.add(f);
        if (ok.isEmpty()) return null;
        Collections.sort(ok, new Comparator<File>() { public int compare(File x, File y) { return x.getName().compareTo(y.getName()); } });
        return ok.get(ok.size() - 1);
    }

    private static byte[] lerArquivo(File f) throws IOException {
        InputStream in = new FileInputStream(f);
        try {
            byte[] d = new byte[(int) f.length()];
            int n = 0, r;
            while (n < d.length && (r = in.read(d, n, d.length - n)) > 0) n += r;
            return d;
        } finally { in.close(); }
    }

    // ------------------------------------------------------------------ PS3
    private void ler() {
        if (lendo || !a.conectado()) return;
        lendo = true;
        jogos = null;
        msg("Lendo os troféus do PS3…", Ui.CINZA);
        redesenhar();
        a.bg(new Runnable() {
            public void run() {
                List<String[]> us = new ArrayList<String[]>();
                List<Jogo> js = new ArrayList<Jogo>();
                String erro = null, u = usuario;
                Ftp f = null;
                try {
                    f = a.conectar();
                    for (Ftp.Item it : f.listar(HOME)) {
                        if (!it.pasta || !it.nome.matches("\\d+")) continue;
                        String nome = "";
                        try { nome = Trofeus.texto(f.lerPedaco(HOME + "/" + it.nome + "/localusername", 0, 64), 0, 64).trim(); }
                        catch (IOException ignored) { }
                        us.add(new String[]{it.nome, nome.isEmpty() ? "Usuário " + Integer.parseInt(it.nome) : nome});
                    }
                    boolean existe = false;
                    for (String[] x : us) if (x[0].equals(u)) existe = true;
                    if (!existe) u = us.isEmpty() ? null : us.get(0)[0];
                    if (u != null) {
                        String base = HOME + "/" + u + "/trophy";
                        List<Ftp.Item> pastas;
                        try { pastas = f.listar(base); } catch (IOException e) { pastas = new ArrayList<Ftp.Item>(); }
                        Pattern tit = Pattern.compile("<title-name>(.*?)</title-name>", Pattern.DOTALL);
                        for (Ftp.Item it : pastas) {
                            if (!it.pasta) continue;
                            final String nomeIt = it.nome;
                            a.ui(new Runnable() { public void run() { msg("Lendo " + nomeIt + "…", Ui.CINZA); } });
                            Jogo j = new Jogo();
                            j.pasta = base + "/" + it.nome;
                            j.codigo = it.nome;
                            try {       // uma pasta que não dá para ler entra na lista com o motivo
                                byte[] usr = f.baixar(j.pasta + "/TROPUSR.DAT");
                                j.total = Trofeus.total(usr);
                                j.ganhos = Trofeus.ganhos(usr);
                            } catch (Ftp.Erro e) {
                                j.erro = "sem TROPUSR.DAT";
                            } catch (Trofeus.Erro e) {
                                j.erro = e.getMessage();
                            } catch (RuntimeException e) {
                                j.erro = String.valueOf(e);
                            }
                            j.nome = it.nome;
                            for (String sfm : new String[]{"TROPCONF.SFM", "TROP.SFM"}) {
                                try {
                                    Matcher m = tit.matcher(new String(f.lerPedaco(j.pasta + "/" + sfm, 0, 8192), Ftp.UTF8));
                                    if (m.find()) { j.nome = android.text.Html.fromHtml(m.group(1).trim()).toString(); break; }
                                } catch (IOException ignored) { }
                            }
                            js.add(j);
                        }
                        Collections.sort(js, new Comparator<Jogo>() { public int compare(Jogo x, Jogo y) { return x.nome.compareToIgnoreCase(y.nome); } });
                    }
                } catch (IOException e) {
                    erro = e.getMessage();
                } finally {
                    if (f != null) f.fechar();
                }
                final List<String[]> fus = us;
                final List<Jogo> fjs = js;
                final String fe = erro, fu = u;
                a.ui(new Runnable() {
                    public void run() {
                        lendo = false;
                        usuarios = fus; usuario = fu; jogos = fjs;
                        if (fe != null) msg("Não consegui ler os troféus (" + fe + ")", Ui.VERMELHO);
                        else msg(fjs.size() + " jogo(s) com troféus. Depois de destravar, NÃO sincronize com a PSN "
                                + "(a Sony pode banir a conta).", Ui.AMARELO);
                        redesenhar();
                    }
                });
            }
        });
    }

    private void escolher(final String cod, boolean deNovo) {
        if (!cod.equals(sel)) marcados.clear();
        sel = cod;
        final Jogo j = jogo(cod);
        if (j != null && !j.erro.isEmpty() && !deNovo) listas.put(cod, new IOException(j.erro));
        else if (j != null && (deNovo || !listas.containsKey(cod) || listas.get(cod) instanceof IOException)) {
            listas.remove(cod);
            a.bg(new Runnable() {
                public void run() {
                    Object r;
                    Ftp f = null;
                    try {
                        f = a.conectar();
                        byte[] usr = f.baixar(j.pasta + "/TROPUSR.DAT");
                        byte[] sfm = null;
                        for (String n : new String[]{"TROP_17.SFM", "TROP_07.SFM", "TROP.SFM", "TROPCONF.SFM"}) {
                            try { sfm = f.baixar(j.pasta + "/" + n); break; } catch (IOException ignored) { }
                        }
                        List<Trofeus.Trofeu> l = Trofeus.resumo(usr, sfm);
                        int g = 0;
                        for (Trofeus.Trofeu t : l) if (t.destravado) g++;
                        j.ganhos = g;
                        r = l;
                    } catch (IOException e) {
                        r = e;
                    } catch (RuntimeException e) {
                        r = new IOException(String.valueOf(e));
                    } finally {
                        if (f != null) f.fechar();
                    }
                    final Object fr = r;
                    a.ui(new Runnable() { public void run() { listas.put(cod, fr); redesenhar(); } });
                }
            });
        }
        redesenhar();
    }

    /** Grava com segurança: primeiro com outro nome, depois troca e confere; se falhar, volta os originais. */
    private static void gravar(Ftp f, String pasta, Map<String, byte[]> novos, Map<String, byte[]> originais) throws IOException {
        List<String> temps = new ArrayList<String>();
        try {
            for (Map.Entry<String, byte[]> e : novos.entrySet()) {
                String tmp = pasta + "/" + e.getKey() + ".pstudo";
                f.enviar(tmp, e.getValue());
                temps.add(tmp);
                if (f.tamanho(tmp) != e.getValue().length) throw new IOException("o PS3 não gravou " + e.getKey() + " inteiro");
            }
            for (String nome : novos.keySet()) {
                try { f.apagarArquivo(pasta + "/" + nome); } catch (IOException ignored) { }
                f.renomear(pasta + "/" + nome + ".pstudo", pasta + "/" + nome);
                temps.remove(pasta + "/" + nome + ".pstudo");
            }
            for (Map.Entry<String, byte[]> e : novos.entrySet())
                if (!Arrays.equals(f.baixar(pasta + "/" + e.getKey()), e.getValue()))
                    throw new IOException(e.getKey() + " no PS3 ficou diferente do esperado");
        } catch (Exception e) {
            for (String nome : novos.keySet()) {
                try { f.enviar(pasta + "/" + nome, originais.get(nome)); } catch (IOException ignored) { }
            }
            throw new IOException(e.getMessage() + ". O PSTudo voltou os arquivos originais; a cópia de segurança está no celular.");
        } finally {
            for (String t : temps) { try { f.apagarArquivo(t); } catch (IOException ignored) { } }
        }
    }

    private void destravar() {
        final Jogo j = jogo(sel);
        if (ocupado || j == null || marcados.isEmpty()) return;
        ocupado = true;
        final List<Integer> ids = new ArrayList<Integer>(marcados);
        final File bk = new File(pastaBackup(), new SimpleDateFormat("yyyy-MM-dd_HH-mm-ss", Locale.ROOT).format(new Date()));
        msg("Fazendo backup e conferindo a assinatura dos troféus… (deixe o PS3 no XMB, sem jogo aberto)", Ui.CINZA);
        atualizarBotoes();
        a.bg(new Runnable() {
            public void run() {
                String m;
                int cor = Ui.VERDE;
                Ftp f = null;
                try {
                    f = a.conectar();
                    Map<String, byte[]> arqs = new LinkedHashMap<String, byte[]>();
                    for (Ftp.Item it : f.listar(j.pasta)) {
                        String n = it.nome.toUpperCase(Locale.ROOT);
                        if (it.pasta || n.endsWith(".PNG")) continue;
                        arqs.put(n, f.baixar(j.pasta + "/" + it.nome));
                    }
                    for (String n : MUDAM) if (!arqs.containsKey(n)) throw new IOException(n + " não existe nesta pasta");
                    if (!bk.mkdirs() && !bk.isDirectory()) throw new IOException("não consegui criar o backup no celular");
                    for (Map.Entry<String, byte[]> e : arqs.entrySet()) {       // backup antes de tudo
                        FileOutputStream o = new FileOutputStream(new File(bk, e.getKey()));
                        try { o.write(e.getValue()); } finally { o.close(); }
                    }
                    Trofeus.Resultado r = Trofeus.destravar(arqs, ids, System.currentTimeMillis());
                    if (r.feitos == 0) m = "Esses troféus já estavam destravados.";
                    else {
                        a.ui(new Runnable() { public void run() { msg("Gravando no PS3…", Ui.CINZA); } });
                        gravar(f, j.pasta, r.novos, arqs);
                        File depois = new File(bk, "depois");       // como ficou: o Desfazer confere antes de voltar
                        if (depois.mkdirs() || depois.isDirectory())
                            for (Map.Entry<String, byte[]> e : r.novos.entrySet()) {
                                FileOutputStream o = new FileOutputStream(new File(depois, e.getKey()));
                                try { o.write(e.getValue()); } finally { o.close(); }
                            }
                        m = "✓ " + r.feitos + " troféu(s) destravado(s). Reinicie o PS3 para aparecerem. Não sincronize com a PSN."
                                + (r.pulouPlatina ? " A platina ficou de fora: ela só vem com todos os troféus do jogo." : "");
                    }
                } catch (IOException e) {
                    m = "Não destravei: " + e.getMessage();
                    cor = Ui.VERMELHO;
                } catch (RuntimeException e) {
                    m = "Não destravei: " + e;
                    cor = Ui.VERMELHO;
                } finally {
                    if (f != null) f.fechar();
                }
                final String fm = m;
                final int fc = cor;
                a.ui(new Runnable() {
                    public void run() {
                        ocupado = false;
                        marcados.clear();
                        msg(fm, fc);
                        escolher(j.codigo, true);
                    }
                });
            }
        });
    }

    private void desfazer() {
        final Jogo j = jogo(sel);
        final File bk = ultimoBackup();
        if (ocupado || j == null || bk == null) return;
        ocupado = true;
        msg("Desfazendo…", Ui.CINZA);
        atualizarBotoes();
        a.bg(new Runnable() {
            public void run() {
                String m;
                int cor = Ui.VERDE;
                Ftp f = null;
                try {
                    Map<String, byte[]> antes = new LinkedHashMap<String, byte[]>(), atuais = new HashMap<String, byte[]>();
                    for (String n : MUDAM) antes.put(n, lerArquivo(new File(bk, n)));
                    f = a.conectar();
                    for (String n : MUDAM) atuais.put(n, f.baixar(j.pasta + "/" + n));
                    for (String n : MUDAM)
                        if (!Arrays.equals(lerArquivo(new File(new File(bk, "depois"), n)), atuais.get(n)))
                            throw new IOException("os troféus mudaram no PS3 depois que o PSTudo destravou (você ganhou algum jogando?). "
                                    + "Desfazer agora apagaria isso, então não mexi.");
                    gravar(f, j.pasta, antes, atuais);
                    bk.renameTo(new File(bk.getPath() + "_desfeito"));     // o próximo "Desfazer" volta mais um passo
                    m = "✓ Desfeito: os troféus voltaram a como estavam em " + bk.getName().replace('_', ' ') + ". Reinicie o PS3.";
                } catch (IOException e) {
                    m = "Não consegui desfazer: " + e.getMessage();
                    cor = Ui.VERMELHO;
                } finally {
                    if (f != null) f.fechar();
                }
                final String fm = m;
                final int fc = cor;
                a.ui(new Runnable() {
                    public void run() { ocupado = false; msg(fm, fc); escolher(j.codigo, true); }
                });
            }
        });
    }
}
