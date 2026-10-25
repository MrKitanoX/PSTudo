package com.mrkitanox.pstudo;

import android.content.ContentResolver;
import android.content.Intent;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.net.Uri;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Aba Enviar jogos: fila de pastas/ISOs/PKGs, envio com progresso e atualizar o XMB. */
public class TabEnviar {
    static class Item {
        Uri uri;            // pasta (árvore) ou arquivo
        boolean pasta;
        String arquivo;     // nome da pasta/arquivo no celular
        String nome;        // nome bonito (TITLE do PARAM.SFO)
        long tamanho = -1;
    }

    static class Cancelado extends IOException { Cancelado() { super("cancelado"); } }

    private final MainActivity a;
    final List<Item> fila = new ArrayList<Item>();
    volatile boolean enviando = false;
    private volatile boolean cancelar = false;
    private String modo = "fila";          // fila | enviando | fim | erro
    private String fimTitulo = "", fimSub = "", fimExtra = "";
    // progresso
    private long enviado, total;
    private int idx, qtd;
    private String jogoAtual = "";
    private long inicio;
    // telas
    private TextView txJogo, txSub, txPct, txRest, txExtra;
    private Ui.Barra barra;
    private TextView btnEnviar, btnXmbFim;

    TabEnviar(MainActivity a) { this.a = a; }

    private int dp(float v) { return a.dp(v); }

    View view() {
        FrameLayout raiz = new FrameLayout(a);
        View corpo;
        if ("enviando".equals(modo)) corpo = telaEnviando();
        else if ("fim".equals(modo) || "erro".equals(modo)) corpo = telaFinal();
        else corpo = fila.isEmpty() ? telaInicio() : telaFila();
        raiz.addView(corpo, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        if (!"enviando".equals(modo)) {
            // canto de baixo à direita: atualizar a lista de jogos do XMB quando quiser
            final TextView xmb = Ui.botao(a, "⟳  Atualizar XMB", "contorno", null);
            xmb.setTextSize(12);
            xmb.setMinHeight(dp(34));
            xmb.setPadding(dp(14), dp(6), dp(14), dp(6));
            xmb.setOnClickListener(new View.OnClickListener() {
                public void onClick(View v) { atualizarXmb(xmb, null); }
            });
            FrameLayout.LayoutParams p = new FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM | Gravity.END);
            p.setMargins(0, 0, dp(14), dp(6));
            raiz.addView(xmb, p);
        }
        return raiz;
    }

    private void redesenhar() { if (a.abaAtual() == 0) a.mostrarAba(0); }

    void statusMudou() {
        if (btnEnviar != null) Ui.ativo(btnEnviar, a.conectado() && !fila.isEmpty());
    }

    // ------------------------------------------------------------------ telas
    private View cartaoGrande(String icone, String titulo, String sub, View.OnClickListener l) {
        LinearLayout c = Ui.coluna(a);
        c.setGravity(Gravity.CENTER);
        c.setBackground(Ui.estados(a, 0xFF0E1A33, Ui.BTN_PRESS, 20, Ui.BORDA));
        c.setPadding(dp(16), dp(22), dp(16), dp(22));
        c.addView(new Ui.Icone(a, icone, Ui.BRANCO), Ui.lp(dp(52), dp(52)));
        TextView t = Ui.texto(a, titulo, 18, Ui.BRANCO, Ui.FORTE);
        t.setPadding(0, dp(10), 0, dp(2));
        c.addView(t);
        c.addView(Ui.texto(a, sub, 13, Ui.CINZA, Ui.NORMAL));
        c.setClickable(true);
        c.setOnClickListener(l);
        return c;
    }

    private View telaInicio() {
        LinearLayout c = Ui.coluna(a);
        c.setPadding(dp(20), dp(24), dp(20), dp(60));
        TextView t = Ui.texto(a, "O que você quer enviar?", 24, Ui.BRANCO, Ui.LEVE);
        t.setGravity(Gravity.CENTER);
        c.addView(t, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 0, 0, 20));
        c.addView(cartaoGrande("pasta", "Pasta do jogo", "Jogos em pasta (BLUS, BLES…)", new View.OnClickListener() {
            public void onClick(View v) { addPasta(); }
        }), Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, 0, 0, 0, 0, 12));
        ((LinearLayout.LayoutParams) c.getChildAt(1).getLayoutParams()).weight = 1;
        c.addView(cartaoGrande("disco", "ISO ou PKG", "Imagens de disco e pacotes", new View.OnClickListener() {
            public void onClick(View v) { addArquivos(); }
        }), Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, 0, 0, 0, 0, 0));
        ((LinearLayout.LayoutParams) c.getChildAt(2).getLayoutParams()).weight = 1;
        return c;
    }

    private View telaFila() {
        LinearLayout c = Ui.coluna(a);
        c.setPadding(dp(16), dp(10), dp(16), dp(52));
        TextView t = Ui.texto(a, "Pronto para enviar", 24, Ui.BRANCO, Ui.LEVE);
        t.setGravity(Gravity.CENTER);
        c.addView(t, Ui.lp(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        long tot = 0;
        boolean calculando = false;
        for (Item i : fila) { if (i.tamanho < 0) calculando = true; else tot += i.tamanho; }
        TextView s = Ui.texto(a, fila.size() + (fila.size() == 1 ? " jogo" : " jogos") + " • "
                + (calculando ? "calculando…" : Caminhos.tamanho(tot)), 14, Ui.CINZA, Ui.NORMAL);
        s.setGravity(Gravity.CENTER);
        c.addView(s, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 2, 0, 10));
        ScrollView sv = new ScrollView(a);
        LinearLayout lista = Ui.coluna(a);
        for (int k = 0; k < fila.size(); k++) {
            final int idxItem = k;
            Item i = fila.get(k);
            LinearLayout l = Ui.linha(a);
            l.setBackground(Ui.fundo(a, 0x0DFFFFFF, 16, Ui.BORDA));
            l.setPadding(dp(16), dp(12), dp(8), dp(12));
            TextView n = Ui.texto(a, i.nome, 15, Ui.BRANCO, Ui.NORMAL);
            n.setSingleLine(true);
            n.setEllipsize(android.text.TextUtils.TruncateAt.END);
            l.addView(n, Ui.lpPeso(1));
            l.addView(Ui.texto(a, i.tamanho < 0 ? "…" : Caminhos.tamanho(i.tamanho), 13, Ui.CINZA, Ui.NORMAL));
            TextView x = Ui.texto(a, "✕", 16, Ui.CINZA, Ui.NORMAL);
            x.setPadding(dp(14), dp(4), dp(10), dp(4));
            x.setOnClickListener(new View.OnClickListener() {
                public void onClick(View v) { fila.remove(idxItem); redesenhar(); }
            });
            l.addView(x);
            lista.addView(l, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 0, 0, 8));
        }
        sv.addView(lista);
        c.addView(sv, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        LinearLayout bts = Ui.linha(a);
        bts.addView(Ui.botao(a, "+ Pasta", "contorno", new View.OnClickListener() {
            public void onClick(View v) { addPasta(); }
        }), Ui.lpPeso(1));
        bts.addView(Ui.espaco(a, 1), Ui.lp(dp(8), 1));
        bts.addView(Ui.botao(a, "+ ISO ou PKG", "contorno", new View.OnClickListener() {
            public void onClick(View v) { addArquivos(); }
        }), Ui.lpPeso(1));
        c.addView(bts, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 8, 0, 8));
        btnEnviar = Ui.botao(a, "Enviar para o PS3", "azul", new View.OnClickListener() {
            public void onClick(View v) { iniciar(); }
        });
        btnEnviar.setTextSize(16);
        btnEnviar.setMinHeight(dp(50));
        c.addView(btnEnviar, Ui.lp(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        Ui.ativo(btnEnviar, a.conectado() && !calculando);
        return c;
    }

    private View telaEnviando() {
        LinearLayout c = Ui.coluna(a);
        c.setGravity(Gravity.CENTER);
        c.setPadding(dp(24), dp(10), dp(24), dp(24));
        txJogo = Ui.texto(a, jogoAtual.isEmpty() ? "Preparando…" : jogoAtual, 24, Ui.BRANCO, Ui.LEVE);
        txJogo.setGravity(Gravity.CENTER);
        c.addView(txJogo);
        txSub = Ui.texto(a, "", 14, Ui.CINZA, Ui.NORMAL);
        c.addView(txSub);
        txPct = Ui.texto(a, "0%", 60, Ui.BRANCO, Ui.LEVE);
        c.addView(txPct, Ui.margem(a, ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 30, 0, 18));
        barra = new Ui.Barra(a);
        c.addView(barra, Ui.lp(ViewGroup.LayoutParams.MATCH_PARENT, dp(10)));
        txRest = Ui.texto(a, "Calculando o tempo…", 14, Ui.CINZA, Ui.NORMAL);
        c.addView(txRest, Ui.margem(a, ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 14, 0, 30));
        c.addView(Ui.botao(a, "Cancelar", "contorno", new View.OnClickListener() {
            public void onClick(View v) { cancelar = true; }
        }), Ui.lp(dp(180), ViewGroup.LayoutParams.WRAP_CONTENT));
        c.addView(Ui.texto(a, "Deixe o app aberto: a tela fica ligada durante o envio.", 12, Ui.CINZA_ESCURO, Ui.NORMAL),
                Ui.margem(a, ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 18, 0, 0));
        mostrarProgresso();
        return c;
    }

    private View telaFinal() {
        boolean ok = "fim".equals(modo);
        LinearLayout c = Ui.coluna(a);
        c.setGravity(Gravity.CENTER);
        c.setPadding(dp(24), dp(10), dp(24), dp(56));
        c.addView(new Ui.Icone(a, ok ? "check" : "alerta", ok ? Ui.VERDE : Ui.VERMELHO), Ui.lp(dp(96), dp(96)));
        TextView t = Ui.texto(a, fimTitulo, 26, Ui.BRANCO, Ui.LEVE);
        t.setGravity(Gravity.CENTER);
        c.addView(t, Ui.margem(a, ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 16, 0, 6));
        TextView s = Ui.texto(a, fimSub, 15, Ui.CINZA, Ui.NORMAL);
        s.setGravity(Gravity.CENTER);
        c.addView(s);
        txExtra = Ui.texto(a, fimExtra, 12, Ui.CINZA_ESCURO, Ui.NORMAL);
        txExtra.setGravity(Gravity.CENTER);
        c.addView(txExtra, Ui.margem(a, ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 10, 0, 26));
        if (ok) {
            btnXmbFim = Ui.botao(a, "Atualizar jogos no XMB", "azul", null);
            btnXmbFim.setOnClickListener(new View.OnClickListener() {
                public void onClick(View v) { atualizarXmb(btnXmbFim, txExtra); }
            });
            c.addView(btnXmbFim, Ui.lp(dp(260), ViewGroup.LayoutParams.WRAP_CONTENT));
            c.addView(Ui.botao(a, "Enviar mais jogos", "contorno", new View.OnClickListener() {
                public void onClick(View v) { fila.clear(); modo = "fila"; redesenhar(); }
            }), Ui.margem(a, dp(260), ViewGroup.LayoutParams.WRAP_CONTENT, 0, 10, 0, 0));
        } else {
            c.addView(Ui.botao(a, "Tentar de novo", "azul", new View.OnClickListener() {
                public void onClick(View v) { modo = "fila"; iniciar(); }
            }), Ui.lp(dp(240), ViewGroup.LayoutParams.WRAP_CONTENT));
            c.addView(Ui.botao(a, "Voltar", "contorno", new View.OnClickListener() {
                public void onClick(View v) { modo = "fila"; redesenhar(); }
            }), Ui.margem(a, dp(240), ViewGroup.LayoutParams.WRAP_CONTENT, 0, 10, 0, 0));
        }
        return c;
    }

    // ------------------------------------------------------------------ fila
    private void addPasta() {
        a.escolherPasta(new MainActivity.Resultado() {
            public void ok(Intent d) {
                Item i = new Item();
                i.uri = d.getData();
                i.pasta = true;
                i.arquivo = Docs.nomePasta(a.getContentResolver(), i.uri);
                i.nome = i.arquivo;
                adicionar(i);
            }
        });
    }

    private void addArquivos() {
        a.escolherArquivos(new MainActivity.Resultado() {
            public void ok(Intent d) {
                for (Uri u : MainActivity.uris(d)) {
                    Item i = new Item();
                    i.uri = u;
                    i.pasta = false;
                    i.arquivo = Docs.nome(a.getContentResolver(), u);
                    String n = i.arquivo.contains(".") ? i.arquivo.substring(0, i.arquivo.lastIndexOf('.')) : i.arquivo;
                    i.nome = n.replace('_', ' ').replace('.', ' ').trim();
                    adicionar(i);
                }
            }
        });
    }

    private void adicionar(final Item i) {
        for (Item x : fila) if (x.uri.equals(i.uri)) return;
        fila.add(i);
        modo = "fila";
        redesenhar();
        a.bg(new Runnable() {     // nome do jogo e tamanho em segundo plano (pastas grandes demoram)
            public void run() {
                ContentResolver cr = a.getContentResolver();
                if (i.pasta) {
                    String t = Docs.tituloJogo(cr, i.uri);
                    if (t != null && !t.isEmpty()) i.nome = t;
                    long s = 0;
                    for (Docs.Arquivo f : Docs.todos(cr, i.uri)) s += f.tamanho;
                    i.tamanho = s;
                } else i.tamanho = Docs.tamanho(cr, i.uri);
                a.ui(new Runnable() { public void run() { if ("fila".equals(modo)) redesenhar(); } });
            }
        });
    }

    // ------------------------------------------------------------------ envio
    private void iniciar() {
        if (enviando || fila.isEmpty() || !a.conectado()) return;
        enviando = true;
        cancelar = false;
        enviado = 0;
        total = 1;
        idx = 0;
        qtd = fila.size();
        jogoAtual = "";
        modo = "enviando";
        a.manterAcordado(true);
        redesenhar();
        final List<Item> copia = new ArrayList<Item>(fila);
        final String escolha = a.prefs.getString("destino", "Automático");
        final boolean pular = a.prefs.getBoolean("pular", true);
        a.bg(new Runnable() {
            public void run() {
                Ftp ftp = null;
                try {
                    ContentResolver cr = a.getContentResolver();
                    // plano: (item, lista de [origem, remoto, tamanho])
                    List<Object[]> planos = new ArrayList<Object[]>();
                    long tot = 0;
                    for (Item i : copia) {
                        String dest = Caminhos.destinoAuto(i.arquivo, i.pasta, escolha).replaceAll("/+$", "");
                        List<Object[]> arqs = new ArrayList<Object[]>();
                        if (i.pasta) {
                            String base = Ftp.paraFtp(i.arquivo);
                            for (Docs.Arquivo f : Docs.todos(cr, i.uri)) {
                                arqs.add(new Object[]{f.id, dest + "/" + base + "/" + Ftp.paraFtp(f.relativo), f.tamanho});
                                tot += f.tamanho;
                            }
                        } else {
                            long t = Docs.tamanho(cr, i.uri);
                            arqs.add(new Object[]{null, dest + "/" + Ftp.paraFtp(i.arquivo), t});
                            tot += t;
                        }
                        planos.add(new Object[]{i, arqs});
                    }
                    total = Math.max(1, tot);
                    ftp = a.conectar();
                    inicio = System.currentTimeMillis();
                    Set<String> cache = new HashSet<String>();
                    for (int k = 0; k < planos.size(); k++) {
                        final Item it = (Item) planos.get(k)[0];
                        idx = k + 1;
                        jogoAtual = it.nome;
                        @SuppressWarnings("unchecked") List<Object[]> arqs = (List<Object[]>) planos.get(k)[1];
                        for (Object[] f : arqs) {
                            if (cancelar) throw new Cancelado();
                            String remoto = (String) f[1];
                            long tam = (Long) f[2];
                            ftp.criarPastasDe(remoto, cache);
                            if (pular && ftp.tamanho(remoto) == tam) { enviado += tam; avisar(); continue; }
                            InputStream in = f[0] == null ? cr.openInputStream(it.uri) : Docs.abrir(cr, it.uri, (String) f[0]);
                            try {
                                ftp.enviar(remoto, in, new Ftp.Progresso() {
                                    public void bytes(long n) throws IOException {
                                        if (cancelar) throw new Cancelado();
                                        enviado += n;
                                        avisar();
                                    }
                                });
                            } finally {
                                try { in.close(); } catch (IOException ignored) { }
                            }
                        }
                    }
                    final int n = planos.size();
                    final long min = Math.max(1, Math.round((System.currentTimeMillis() - inicio) / 60000.0));
                    terminar("fim", "Tudo pronto!", n + (n == 1 ? " jogo enviado" : " jogos enviados") + " para o PS3 em " + min + " min.",
                            "Toque em Atualizar jogos no XMB para eles aparecerem (o PS3 precisa estar no XMB, fora de jogo).");
                } catch (Cancelado c) {
                    terminar("fila", null, null, null);
                } catch (final Exception e) {
                    String m = String.valueOf(e.getMessage());
                    String tit, sub;
                    if (e instanceof java.net.SocketTimeoutException || e instanceof java.net.ConnectException || m.contains("timed out")) {
                        tit = "Não consegui falar com o PS3.";
                        sub = "Confira se ele está ligado, com o HEN ativado e na mesma rede.";
                    } else if (m.startsWith("452") || m.startsWith("552")) {
                        tit = "O PS3 ficou sem espaço.";
                        sub = "Libere espaço no HD do console e tente de novo.";
                    } else if (m.startsWith("530")) {
                        tit = "O PS3 recusou o login.";
                        sub = "Confira o usuário e a senha nas configurações.";
                    } else {
                        tit = "A conexão caiu no meio do envio.";
                        sub = "Tente de novo: o que já foi enviado não será mandado outra vez.";
                    }
                    terminar("erro", tit, sub, "Detalhe: " + (m.length() > 120 ? m.substring(0, 120) : m));
                } finally {
                    if (ftp != null) ftp.fechar();
                }
            }
        });
    }

    private long ultimoAviso = 0;

    private void avisar() {
        long agora = System.currentTimeMillis();
        if (agora - ultimoAviso < 150) return;
        ultimoAviso = agora;
        a.ui(new Runnable() { public void run() { mostrarProgresso(); } });
    }

    private void mostrarProgresso() {
        float f = Math.min(1f, enviado / (float) Math.max(1, total));
        int pct = (int) (f * 100);
        a.marcarAba(0, enviando ? "↑ " + pct + "%" : null);
        if (txPct == null || a.abaAtual() != 0 || !"enviando".equals(modo)) return;
        txPct.setText(pct + "%");
        barra.set(f);
        if (!jogoAtual.isEmpty()) txJogo.setText(jogoAtual);
        txSub.setText(qtd > 1 ? "Jogo " + idx + " de " + qtd : "");
        double dt = (System.currentTimeMillis() - inicio) / 1000.0;
        if (dt > 3 && enviado > 0) {
            double vel = enviado / dt;
            txRest.setText(Caminhos.restante((total - enviado) / vel) + "   ·   " + Caminhos.tamanho((long) vel) + "/s");
        }
    }

    private void terminar(final String m, final String tit, final String sub, final String extra) {
        a.ui(new Runnable() {
            public void run() {
                enviando = false;
                a.manterAcordado(false);
                a.marcarAba(0, null);
                if ("fim".equals(m)) {
                    fila.clear();
                    if (a.prefs.getBoolean("som", true)) tocarSom();
                    if (a.abaAtual() != 0) a.aviso("Envio concluído!", false);
                } else if ("erro".equals(m) && a.abaAtual() != 0) a.aviso("O envio parou. Abra Enviar jogos para ver.", true);
                modo = m;
                fimTitulo = tit == null ? "" : tit;
                fimSub = sub == null ? "" : sub;
                fimExtra = extra == null ? "" : extra;
                redesenhar();
            }
        });
    }

    private void tocarSom() {
        try {
            Ringtone r = RingtoneManager.getRingtone(a, RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION));
            if (r != null) r.play();
        } catch (Exception ignored) { }
    }

    // ------------------------------------------------------------------ XMB
    void atualizarXmb(final TextView botao, final TextView texto) {
        if (!botao.isEnabled()) return;
        if (!a.conectado()) { a.aviso("Conecte o PS3 primeiro.", false); return; }
        final CharSequence antes = botao.getText();
        Ui.ativo(botao, false);
        botao.setText("Atualizando…");
        if (texto != null) texto.setText("Atualizando a lista de jogos do webMAN e recarregando o XMB…");
        final String ip = a.ip();
        a.bg(new Runnable() {
            public void run() {
                String msg;
                int cor;
                try {
                    if (WebMan.atualizarXmb(ip)) msg = "Pronto! O XMB recarregou com os jogos novos.";
                    else msg = "Lista de jogos atualizada. Saia e entre no usuário do PS3 para ver os jogos.";
                    cor = Ui.VERDE;
                } catch (IOException e) {
                    msg = "Não consegui atualizar o XMB (" + e.getMessage() + "). Tente com o PS3 no XMB.";
                    cor = Ui.VERMELHO;
                }
                final String fm = msg;
                final int fc = cor;
                a.ui(new Runnable() {
                    public void run() {
                        botao.setText(texto != null && fc == Ui.VERDE ? "Atualizar de novo" : antes);
                        Ui.ativo(botao, true);
                        if (texto != null) { texto.setText(fm); texto.setTextColor(fc); }
                        else a.aviso(fm, true);
                    }
                });
            }
        });
    }
}
