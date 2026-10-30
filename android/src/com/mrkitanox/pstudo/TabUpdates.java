package com.mrkitanox.pstudo;

import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.SocketTimeoutException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/** Aba Updates: busca os updates dos jogos no servidor da Sony e instala no PS3. */
public class TabUpdates {
    static final int ABA = 4;

    private final MainActivity a;
    private List<Updates.Jogo> jogos = null;
    private boolean lendo = false;
    private String sel = null;
    private final Map<String, Object> info = new HashMap<String, Object>();   // Info ou IOException
    private final Set<String> buscando = new HashSet<String>();
    private final List<String> digitados = new ArrayList<String>();
    private boolean baixando = false;
    private Updates.Leitor leitorAtual = null;
    private volatile boolean cancelar = false;
    private String msg = "";
    private int msgCor = Ui.CINZA;
    private float frac = -1;

    private TextView lblMsg, bInstalar, bCancelar, bLer;
    private Ui.Barra barra;

    TabUpdates(MainActivity a) { this.a = a; }

    private int dp(float v) { return a.dp(v); }

    private boolean ativa() { return a.abaAtual() == ABA && lblMsg != null; }

    void statusMudou() {
        if (a.abaAtual() != ABA) return;
        if (a.conectado() && jogos == null && !lendo) lerJogos();
        else a.mostrarAba(ABA);
    }

    private void msg(String t, int cor) {
        msg = t;
        msgCor = cor;
        if (lblMsg != null) { lblMsg.setText(L.t(t)); lblMsg.setTextColor(cor); }
    }

    private void progresso(float f) {
        frac = f;
        if (barra != null) {
            barra.setVisibility(f < 0 ? View.GONE : View.VISIBLE);
            if (f >= 0) barra.set(f);
        }
    }

    private void redesenhar() { if (a.abaAtual() == ABA) a.mostrarAba(ABA); }

    View view() {
        lblMsg = null;
        View v = sel == null ? telaJogos() : telaUpdates();
        if (sel == null && jogos == null && !lendo && a.conectado())
            a.h.post(new Runnable() { public void run() { lerJogos(); } });   // depois de montar a tela
        return v;
    }

    // ------------------------------------------------------------------ telas
    private LinearLayout base(LinearLayout c) {
        c.setPadding(dp(14), dp(6), dp(14), dp(10));
        return c;
    }

    private void rodape(LinearLayout c) {
        barra = new Ui.Barra(a);
        c.addView(barra, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, dp(5), 0, 8, 0, 6));
        lblMsg = Ui.texto(a, msg, 13, msgCor, Ui.NORMAL);
        c.addView(lblMsg, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 2, 0, 2, 8));
        progresso(frac);
    }

    private View telaJogos() {
        LinearLayout c = base(Ui.coluna(a));
        c.addView(Ui.texto(a, "Updates de jogos", 22, Ui.BRANCO, Ui.LEVE));
        c.addView(Ui.texto(a, "Direto do servidor da Sony, o mesmo que o PS3 usa.", 12, Ui.CINZA, Ui.NORMAL),
                Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 2, 0, 10));
        LinearLayout busca = Ui.linha(a);
        final EditText campo = new EditText(a);
        campo.setSingleLine(true);
        campo.setHint(L.t("Código do jogo (ex.: BLUS30443)"));
        campo.setHintTextColor(Ui.CINZA_ESCURO);
        campo.setTextColor(Ui.BRANCO);
        campo.setTextSize(14);
        campo.setBackground(Ui.fundo(a, Ui.PAINEL, 18, 0xFF26324D));
        campo.setPadding(dp(14), dp(8), dp(14), dp(8));
        campo.setImeOptions(EditorInfo.IME_ACTION_SEARCH);
        campo.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            public boolean onEditorAction(TextView v, int id, KeyEvent e) { buscarCodigo(campo); return true; }
        });
        busca.addView(campo, Ui.lpPeso(1));
        busca.addView(Ui.botao(a, "Buscar", "normal", new View.OnClickListener() {
            public void onClick(View v) { buscarCodigo(campo); }
        }), Ui.margem(a, ViewGroup.LayoutParams.WRAP_CONTENT, dp(42), 8, 0, 0, 0));
        c.addView(busca);

        LinearLayout cab = Ui.linha(a);
        cab.addView(Ui.texto(a, "Jogos no PS3", 15, Ui.BRANCO, Ui.FORTE), Ui.lpPeso(1));
        bLer = Ui.botao(a, "⟳ Ler de novo", "contorno", new View.OnClickListener() {
            public void onClick(View v) { lerJogos(); }
        });
        bLer.setTextSize(12);
        bLer.setMinHeight(dp(34));
        bLer.setPadding(dp(12), dp(4), dp(12), dp(4));
        cab.addView(bLer);
        Ui.ativo(bLer, a.conectado() && !lendo && !baixando);
        c.addView(cab, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 14, 0, 6));

        ScrollView sv = new ScrollView(a);
        LinearLayout lista = Ui.coluna(a);
        List<Updates.Jogo> todos = new ArrayList<Updates.Jogo>();
        for (String id : digitados) if (achar(id) == null) todos.add(new Updates.Jogo(id));
        if (jogos != null) todos.addAll(jogos);
        if (todos.isEmpty()) {
            String t = lendo ? "Lendo os jogos do PS3…" : !a.conectado() ? "Conecte o PS3 para ver os jogos."
                    : jogos != null ? "Nenhum jogo encontrado. Digite o código do jogo acima." : "";
            TextView tv = Ui.texto(a, t, 13, Ui.CINZA, Ui.NORMAL);
            tv.setGravity(Gravity.CENTER);
            tv.setPadding(0, dp(30), 0, dp(30));
            lista.addView(tv, Ui.lp(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        }
        for (final Updates.Jogo j : todos) {
            LinearLayout l = Ui.coluna(a);
            l.setBackground(Ui.estados(a, Ui.CARD, Ui.LINHA_SEL, 12, 0));
            l.setPadding(dp(14), dp(10), dp(14), dp(10));
            Object in = info.get(j.id);
            String titulo = !j.titulo.isEmpty() ? j.titulo : in instanceof Updates.Info && !((Updates.Info) in).titulo.isEmpty()
                    ? ((Updates.Info) in).titulo : j.id;
            TextView n = Ui.texto(a, titulo, 14, Ui.BRANCO, Ui.FORTE);
            n.setSingleLine(true);
            n.setEllipsize(android.text.TextUtils.TruncateAt.END);
            l.addView(n);
            String sub = j.id + (j.instalado.isEmpty() ? "" : "  •  v" + j.instalado);
            int corSub = Ui.CINZA_ESCURO;
            if (in instanceof Updates.Info) {
                int f = faltando(j.id).size();
                sub += f > 0 ? "  •  " + f + " update(s) novo(s)" : ((Updates.Info) in).pacotes.isEmpty() ? "  •  sem updates" : "  •  atualizado";
                if (f > 0) corSub = 0xFF7FB2F0;
            }
            l.addView(Ui.texto(a, sub, 12, corSub, Ui.NORMAL));
            l.setClickable(true);
            l.setOnClickListener(new View.OnClickListener() { public void onClick(View v) { escolher(j.id, false); } });
            lista.addView(l, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 0, 0, 6));
        }
        sv.addView(lista);
        c.addView(sv, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        rodape(c);
        return c;
    }

    private View telaUpdates() {
        LinearLayout c = base(Ui.coluna(a));
        LinearLayout topo = Ui.linha(a);
        TextView voltar = Ui.botao(a, "←", "normal", new View.OnClickListener() {
            public void onClick(View v) { sel = null; if (!baixando) msg("", Ui.CINZA); redesenhar(); }
        });
        voltar.setPadding(dp(14), dp(4), dp(14), dp(4));
        topo.addView(voltar, Ui.margem(a, ViewGroup.LayoutParams.WRAP_CONTENT, dp(40), 0, 0, 10, 0));
        Object in = info.get(sel);
        Updates.Jogo j = achar(sel);
        String nome = j != null && !j.titulo.isEmpty() ? j.titulo
                : in instanceof Updates.Info && !((Updates.Info) in).titulo.isEmpty() ? ((Updates.Info) in).titulo : sel;
        LinearLayout tt = Ui.coluna(a);
        TextView tn = Ui.texto(a, nome, 17, Ui.BRANCO, Ui.FORTE);
        tn.setMaxLines(2);
        tt.addView(tn);
        String inst = instalado(sel);
        tt.addView(Ui.texto(a, sel + (inst.isEmpty() ? "" : "  •  no PS3: v" + inst), 12, Ui.CINZA, Ui.NORMAL));
        topo.addView(tt, Ui.lpPeso(1));
        c.addView(topo, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 4, 0, 10));

        ScrollView sv = new ScrollView(a);
        LinearLayout lista = Ui.coluna(a);
        if (buscando.contains(sel)) aviso(lista, "Perguntando ao servidor da Sony…", Ui.CINZA);
        else if (in instanceof IOException) {
            aviso(lista, "Não consegui falar com o servidor da Sony.\n(" + ((IOException) in).getMessage() + ")", Ui.VERMELHO);
            lista.addView(Ui.botao(a, "Tentar de novo", "normal", new View.OnClickListener() {
                public void onClick(View v) { escolher(sel, true); }
            }), Ui.lp(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        } else if (in instanceof Updates.Info) {
            Updates.Info inf = (Updates.Info) in;
            if (inf.pacotes.isEmpty()) aviso(lista, "A Sony não tem updates para este jogo.", Ui.CINZA);
            for (Updates.Pacote pk : inf.pacotes) {
                boolean novo = Updates.comparar(pk.versao, inst.isEmpty() ? "0" : inst) > 0;
                LinearLayout l = Ui.linha(a);
                l.setBackground(Ui.fundo(a, Ui.CARD, 12, 0));
                l.setPadding(dp(14), dp(10), dp(14), dp(10));
                LinearLayout col = Ui.coluna(a);
                col.addView(Ui.texto(a, "Versão " + pk.versao, 14, Ui.BRANCO, Ui.FORTE));
                col.addView(Ui.texto(a, tamanho(pk.tamanho) + (pk.fw.isEmpty() ? "" : "  •  precisa do sistema " + Updates.fw(pk.fw)),
                        12, Ui.CINZA, Ui.NORMAL));
                l.addView(col, Ui.lpPeso(1));
                l.addView(Ui.texto(a, novo ? "novo" : "✓ instalado", 12, novo ? 0xFF7FB2F0 : Ui.VERDE, Ui.FORTE));
                lista.addView(l, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 0, 0, 6));
            }
            if (!baixando && msg.isEmpty() && !inf.pacotes.isEmpty()) {
                List<Updates.Pacote> f = faltando(sel);
                long total = 0;
                for (Updates.Pacote pk : f) total += pk.tamanho;
                if (f.isEmpty()) { msg = "Este jogo já está com o último update."; msgCor = Ui.VERDE; }
                else { msg = f.size() + " update(s) para instalar  •  " + tamanho(total); msgCor = Ui.CINZA; }
            }
        }
        sv.addView(lista);
        c.addView(sv, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        rodape(c);

        LinearLayout b = Ui.linha(a);
        bCancelar = Ui.botao(a, "Cancelar", "perigo", new View.OnClickListener() {
            public void onClick(View v) { cancelarTudo(); }
        });
        b.addView(bCancelar, Ui.margem(a, ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 0, 8, 0));
        bCancelar.setVisibility(baixando ? View.VISIBLE : View.GONE);
        boolean tem = in instanceof Updates.Info && !((Updates.Info) in).pacotes.isEmpty();
        List<Updates.Pacote> falta = tem ? faltando(sel) : new ArrayList<Updates.Pacote>();
        bInstalar = Ui.botao(a, baixando ? "Trabalhando…" : (falta.isEmpty() && tem) ? "Já está atualizado" : "Instalar no PS3",
                "azul", new View.OnClickListener() { public void onClick(View v) { instalar(); } });
        bInstalar.setMinHeight(dp(50));
        b.addView(bInstalar, Ui.lpPeso(1));
        Ui.ativo(bInstalar, !baixando && !falta.isEmpty() && a.conectado());
        c.addView(b, Ui.lp(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return c;
    }

    private void aviso(LinearLayout l, String t, int cor) {
        TextView tv = Ui.texto(a, t, 13, cor, Ui.NORMAL);
        tv.setGravity(Gravity.CENTER);
        tv.setPadding(0, dp(30), 0, dp(16));
        l.addView(tv, Ui.lp(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
    }

    // ------------------------------------------------------------------ dados
    private Updates.Jogo achar(String id) {
        if (jogos != null) for (Updates.Jogo j : jogos) if (j.id.equals(id)) return j;
        return null;
    }

    private String instalado(String id) {
        Updates.Jogo j = achar(id);
        return j == null ? "" : j.instalado;
    }

    private List<Updates.Pacote> faltando(String id) {
        List<Updates.Pacote> r = new ArrayList<Updates.Pacote>();
        Object in = info.get(id);
        if (!(in instanceof Updates.Info)) return r;
        String inst = instalado(id);
        for (Updates.Pacote pk : ((Updates.Info) in).pacotes)
            if (Updates.comparar(pk.versao, inst.isEmpty() ? "0" : inst) > 0) r.add(pk);
        return r;
    }

    static String tamanho(long b) {
        double v = b;
        String[] un = {"B", "KB", "MB", "GB"};
        int i = 0;
        while (v >= 1024 && i < un.length - 1) { v /= 1024; i++; }
        return String.format(Locale.ROOT, "%.1f %s", v, un[i]).replace('.', ',');
    }

    // ------------------------------------------------------------------ ações
    private void buscarCodigo(EditText campo) {
        String id = Updates.normalizar(campo.getText().toString());
        InputMethodManager imm = (InputMethodManager) a.getSystemService(android.content.Context.INPUT_METHOD_SERVICE);
        if (imm != null) imm.hideSoftInputFromWindow(campo.getWindowToken(), 0);
        if (id == null) { msg("Digite o código do jogo, como BLUS30443 (fica na capa ou no nome da ISO).", Ui.AMARELO); return; }
        if (!digitados.contains(id)) digitados.add(0, id);
        escolher(id, true);
    }

    private void lerJogos() {
        if (lendo || !a.conectado()) return;
        lendo = true;
        jogos = null;
        msg("Lendo os jogos do PS3…", Ui.CINZA);
        redesenhar();
        a.bg(new Runnable() {
            public void run() {
                List<Updates.Jogo> r = null;
                String erro = null;
                Ftp f = null;
                try {
                    f = a.conectar();
                    r = Updates.listarJogos(f, new Updates.Aviso() {
                        public void texto(final String t) { a.ui(new Runnable() { public void run() { msg(t, Ui.CINZA); } }); }
                    });
                } catch (IOException e) {
                    erro = e.getMessage();
                } finally {
                    if (f != null) f.fechar();
                }
                final List<Updates.Jogo> fr = r;
                final String fe = erro;
                a.ui(new Runnable() {
                    public void run() {
                        lendo = false;
                        jogos = fr != null ? fr : new ArrayList<Updates.Jogo>();
                        if (fe != null) msg("Não consegui ler os jogos (" + fe + ")", Ui.VERMELHO);
                        else msg(jogos.isEmpty() ? "Não achei jogos no PS3. Digite o código do jogo acima."
                                : jogos.size() + " jogo(s) encontrado(s). Toque num jogo para ver os updates.", Ui.CINZA);
                        redesenhar();
                    }
                });
            }
        });
    }

    private void escolher(final String id, boolean deNovo) {
        sel = id;
        if (!baixando) msg("", Ui.CINZA);
        if (deNovo || !info.containsKey(id) || info.get(id) instanceof IOException) {
            info.remove(id);
            buscando.add(id);
            a.bg(new Runnable() {
                public void run() {
                    Object r;
                    try { r = Updates.buscar(id); } catch (IOException e) { r = e; }
                    final Object fr = r;
                    a.ui(new Runnable() {
                        public void run() { buscando.remove(id); info.put(id, fr); redesenhar(); }
                    });
                }
            });
        }
        redesenhar();
    }

    private void cancelarTudo() {
        cancelar = true;
        Updates.Leitor l = leitorAtual;
        if (l != null) l.cancelado = true;
        msg("Cancelando…", Ui.AMARELO);
    }

    private void instalar() {
        final String id = sel;
        final List<Updates.Pacote> lista = faltando(id);
        if (baixando || lista.isEmpty() || !a.conectado()) return;
        baixando = true;
        cancelar = false;
        a.manterAcordado(true);
        long t = 0;
        for (Updates.Pacote pk : lista) t += pk.tamanho;
        final long total = Math.max(1, t);
        final String ip = a.ip();
        progresso(0);
        redesenhar();
        a.bg(new Runnable() {
            long feito = 0, ultimo = 0, t0 = System.currentTimeMillis();

            void avisar(final String s, final int cor) { a.ui(new Runnable() { public void run() { msg(s, cor); } }); }

            public void run() {
                String fim;
                int cor = Ui.VERDE;
                Ftp f = null;
                try {
                    f = a.conectar();
                    try { f.criarPasta(Updates.PASTA); } catch (IOException ignored) { }
                    List<Updates.Pacote> prontos = new ArrayList<Updates.Pacote>();
                    for (int i = 0; i < lista.size(); i++) {
                        final Updates.Pacote pk = lista.get(i);
                        final String etapa = "Baixando a versão " + pk.versao + " (" + (i + 1) + " de " + lista.size() + ")";
                        avisar(etapa + "…", Ui.CINZA);
                        String destino = Updates.PASTA + "/" + Ftp.paraFtp(Updates.nomePkg(pk.url));
                        if (f.tamanho(destino) == pk.tamanho) { feito += pk.tamanho; prontos.add(pk); continue; }
                        HttpURLConnection c = Updates.abrir(pk.url, 60000);
                        try {
                            final Updates.Leitor l = new Updates.Leitor(c.getInputStream());
                            leitorAtual = l;
                            if (cancelar) l.cancelado = true;
                            try {
                                f.enviar(destino, l, new Ftp.Progresso() {
                                    public void bytes(long n) {
                                        feito += n;
                                        long agora = System.currentTimeMillis();
                                        if (agora - ultimo < 300) return;
                                        ultimo = agora;
                                        final float fr = feito / (float) total;
                                        double vel = feito / Math.max(0.5, (agora - t0) / 1000.0);
                                        final String s = etapa + "  •  " + tamanho(feito) + " de " + tamanho(total)
                                                + "  •  " + tamanho((long) vel) + "/s";
                                        a.ui(new Runnable() { public void run() { progresso(fr); msg(s, Ui.CINZA); } });
                                    }
                                });
                                l.conferir(pk);
                            } catch (IOException e) {
                                try { f.apagarArquivo(destino); } catch (IOException ignored) { }
                                throw e;
                            }
                        } finally {
                            leitorAtual = null;
                            c.disconnect();
                        }
                        prontos.add(pk);
                    }
                    a.ui(new Runnable() { public void run() { progresso(-1); } });
                    boolean manual = false;
                    for (int i = 0; i < prontos.size() && !manual; i++) {
                        if (cancelar) throw new IOException("cancelado");
                        Updates.Pacote pk = prontos.get(i);
                        avisar("Instalando a versão " + pk.versao + " no PS3 (" + (i + 1) + " de " + prontos.size()
                                + ")… fique no XMB, sem abrir jogos.", Ui.CINZA);
                        String destino = Updates.PASTA + "/" + Ftp.paraFtp(Updates.nomePkg(pk.url));
                        Ftp[] con = {f};
                        try {
                            if (!instalarNoPs3(con, ip, id, pk, destino)) manual = true;
                        } finally {
                            f = con[0];
                        }
                    }
                    final String nova = Updates.versaoInstalada(f = garantirConexao(f), id);
                    a.ui(new Runnable() {
                        public void run() {
                            Updates.Jogo j = achar(id);
                            if (j != null && !nova.isEmpty() && Updates.comparar(nova, j.instalado.isEmpty() ? "0" : j.instalado) > 0)
                                j.instalado = nova;
                        }
                    });
                    fim = manual ? "✓ " + prontos.size() + " update(s) em /dev_hdd0/packages. Para instalar, no PS3 abra "
                            + "Package Manager › Install Package Files › Standard, do mais antigo para o mais novo."
                            : "✓ " + prontos.size() + " update(s) instalado(s) no PS3.";
                } catch (IOException e) {
                    fim = cancelar ? "Cancelado." : "Não deu certo: " + e.getMessage();
                    cor = cancelar ? Ui.AMARELO : Ui.VERMELHO;
                } catch (RuntimeException e) {
                    fim = "Não deu certo: " + e;
                    cor = Ui.VERMELHO;
                } finally {
                    if (f != null) f.fechar();
                }
                final String ff = fim;
                final int fc = cor;
                a.ui(new Runnable() {
                    public void run() {
                        baixando = false;
                        a.manterAcordado(false);
                        progresso(-1);
                        msg(ff, fc);
                        redesenhar();
                        if (a.abaAtual() != ABA) a.aviso(ff, true);
                    }
                });
            }
        });
    }

    private Ftp garantirConexao(Ftp f) { return Updates.garantirConexao(a, f); }

    private boolean instalarNoPs3(Ftp[] con, String ip, final String id, final Updates.Pacote pk, String destino)
            throws IOException {
        return Updates.instalarPkg(a, con, destino, "a versão " + pk.versao, new Updates.Parar() {
            public void checar() throws IOException { if (cancelar) throw new IOException("cancelado"); }
        }, new Updates.Pronto() {
            public boolean pronto(Ftp f) { return Updates.comparar(Updates.versaoInstalada(f, id), pk.versao) >= 0; }
        });
    }
}
