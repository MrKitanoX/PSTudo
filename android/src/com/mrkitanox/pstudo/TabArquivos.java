package com.mrkitanox.pstudo;

import android.content.ContentResolver;
import android.content.DialogInterface;
import android.content.Intent;
import android.graphics.Typeface;
import android.net.Uri;
import android.provider.DocumentsContract;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.EditorInfo;
import android.widget.AdapterView;
import android.widget.BaseAdapter;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Aba Arquivos: navegar, pesquisar, marcar vários, enviar, baixar, renomear, apagar e editar textos. */
public class TabArquivos {
    private final MainActivity a;
    private String caminho = "/dev_hdd0";
    private List<Ftp.Item> todos = new ArrayList<Ftp.Item>();
    private List<Ftp.Item> itens = new ArrayList<Ftp.Item>();
    private final Set<String> marcados = new HashSet<String>();
    private boolean fundo = false;           // mostrando resultado da pesquisa nas subpastas
    private int buscaId = 0;
    private boolean ocupado = false;
    private String textoBusca = "";
    private String statusTxt = "";
    private int statusCor = Ui.CINZA;

    private TextView lblCaminho, lblStatus, lblSel, btnTudo, btnFundo;
    private TextView bEditar, bBaixar, bRenomear, bApagar, bVoltar;
    private EditText busca;
    private ListView lista;
    private Adaptador adaptador;

    TabArquivos(MainActivity a) { this.a = a; }

    private int dp(float v) { return a.dp(v); }

    private boolean ativo() { return a.abaAtual() == 1 && lista != null; }

    void statusMudou() { if (ativo() && a.conectado() && todos.isEmpty()) listar(); }

    View view() {
        LinearLayout c = Ui.coluna(a);
        c.setPadding(dp(12), dp(6), dp(12), dp(6));
        LinearLayout topo = Ui.linha(a);
        bVoltar = Ui.botao(a, "←", "normal", new View.OnClickListener() {
            public void onClick(View v) { ir(Caminhos.pai(caminho)); }
        });
        topo.addView(bVoltar, Ui.lp(dp(48), dp(40)));
        lblCaminho = Ui.texto(a, Ftp.legivel(caminho), 15, Ui.BRANCO, Ui.FORTE);
        lblCaminho.setSingleLine(true);
        lblCaminho.setEllipsize(android.text.TextUtils.TruncateAt.START);
        lblCaminho.setPadding(dp(10), 0, dp(6), 0);
        topo.addView(lblCaminho, Ui.lpPeso(1));
        topo.addView(Ui.botao(a, "⟳", "normal", new View.OnClickListener() {
            public void onClick(View v) { listar(); }
        }), Ui.lp(dp(48), dp(40)));
        c.addView(topo);

        HorizontalScrollView hs = new HorizontalScrollView(a);
        hs.setHorizontalScrollBarEnabled(false);
        LinearLayout chips = Ui.linha(a);
        String[][] atalhos = {{"HD", "/dev_hdd0"}, {"Jogos", "/dev_hdd0/GAMES"}, {"ISOs", "/dev_hdd0/PS3ISO"},
                {"Pacotes", "/dev_hdd0/packages"}, {"Plugins", "/dev_hdd0/plugins"}, {"Pendrive", "/dev_usb000"}};
        for (final String[] at : atalhos) {
            TextView b = Ui.botao(a, at[0], "normal", new View.OnClickListener() {
                public void onClick(View v) { ir(at[1]); }
            });
            b.setTextSize(13);
            b.setMinHeight(dp(36));
            chips.addView(b, Ui.margem(a, ViewGroup.LayoutParams.WRAP_CONTENT, dp(36), 0, 0, 6, 0));
        }
        hs.addView(chips);
        c.addView(hs, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 8, 0, 6));

        LinearLayout lb = Ui.linha(a);
        busca = new EditText(a);
        busca.setSingleLine(true);
        busca.setHint(L.t("Pesquisar nesta pasta…"));
        busca.setHintTextColor(Ui.CINZA_ESCURO);
        busca.setTextColor(Ui.BRANCO);
        busca.setTextSize(14);
        busca.setBackground(Ui.fundo(a, Ui.PAINEL, 18, 0xFF26324D));
        busca.setPadding(dp(14), dp(8), dp(14), dp(8));
        busca.setImeOptions(EditorInfo.IME_ACTION_SEARCH);
        busca.setText(textoBusca);
        busca.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int i, int j, int k) { }
            public void onTextChanged(CharSequence s, int i, int j, int k) { }
            public void afterTextChanged(Editable s) {
                textoBusca = s.toString();
                if (fundo) { fundo = false; buscaId++; }
                filtrar(false);
            }
        });
        busca.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            public boolean onEditorAction(TextView v, int id, KeyEvent e) { buscarFundo(); return true; }
        });
        lb.addView(busca, new LinearLayout.LayoutParams(0, dp(40), 1));
        btnFundo = Ui.botao(a, "Subpastas", "normal", new View.OnClickListener() {
            public void onClick(View v) { buscarFundo(); }
        });
        btnFundo.setTextSize(13);
        lb.addView(btnFundo, Ui.margem(a, ViewGroup.LayoutParams.WRAP_CONTENT, dp(40), 6, 0, 0, 0));
        lb.addView(Ui.botao(a, "✕", "normal", new View.OnClickListener() {
            public void onClick(View v) { limparBusca(); }
        }), Ui.margem(a, dp(44), dp(40), 6, 0, 0, 0));
        c.addView(lb);

        lista = new ListView(a);
        lista.setDivider(null);
        lista.setDividerHeight(dp(2));
        lista.setSelector(android.R.color.transparent);
        adaptador = new Adaptador();
        lista.setAdapter(adaptador);
        lista.setOnItemClickListener(new AdapterView.OnItemClickListener() {
            public void onItemClick(AdapterView<?> p, View v, int pos, long id) {
                if (!marcados.isEmpty()) alternar(pos);
                else abrir(pos);
            }
        });
        lista.setOnItemLongClickListener(new AdapterView.OnItemLongClickListener() {
            public boolean onItemLongClick(AdapterView<?> p, View v, int pos, long id) { alternar(pos); return true; }
        });
        c.addView(lista, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));

        LinearLayout st = Ui.linha(a);
        lblStatus = Ui.texto(a, statusTxt, 12, statusCor, Ui.NORMAL);
        lblStatus.setMaxLines(2);
        st.addView(lblStatus, Ui.lpPeso(1));
        lblSel = Ui.texto(a, "", 12, Ui.BRANCO, Ui.NORMAL);
        st.addView(lblSel, Ui.margem(a, ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, 6, 0, 8, 0));
        btnTudo = Ui.texto(a, "Marcar tudo", 12, 0xFF7FB2F0, Ui.FORTE);
        btnTudo.setPadding(dp(6), dp(6), dp(4), dp(6));
        btnTudo.setOnClickListener(new View.OnClickListener() { public void onClick(View v) { marcarTudo(); } });
        st.addView(btnTudo);
        c.addView(st, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 2, 4, 0, 2));

        HorizontalScrollView ha = new HorizontalScrollView(a);
        ha.setHorizontalScrollBarEnabled(false);
        LinearLayout ac = Ui.linha(a);
        ac.addView(acao("Enviar arquivos", "normal", new View.OnClickListener() { public void onClick(View v) { enviarArquivos(); } }));
        ac.addView(acao("Nova pasta", "normal", new View.OnClickListener() { public void onClick(View v) { novaPasta(); } }));
        bEditar = acao("Editar", "normal", new View.OnClickListener() { public void onClick(View v) { editar(); } });
        bBaixar = acao("Baixar", "normal", new View.OnClickListener() { public void onClick(View v) { baixar(); } });
        bRenomear = acao("Renomear", "normal", new View.OnClickListener() { public void onClick(View v) { renomear(); } });
        bApagar = acao("Apagar", "perigo", new View.OnClickListener() { public void onClick(View v) { apagar(); } });
        ac.addView(bEditar);
        ac.addView(bBaixar);
        ac.addView(bRenomear);
        ac.addView(bApagar);
        ha.addView(ac);
        c.addView(ha, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 4, 0, 0));

        botoes();
        if (todos.isEmpty() && !fundo) listar();
        return c;
    }

    private TextView acao(String t, String estilo, View.OnClickListener l) {
        TextView b = Ui.botao(a, t, estilo, l);
        b.setTextSize(13);
        b.setLayoutParams(Ui.margem(a, ViewGroup.LayoutParams.WRAP_CONTENT, dp(40), 0, 0, 6, 0));
        return b;
    }

    private void status(String t, int cor) {
        statusTxt = t;
        statusCor = cor;
        if (lblStatus != null) { lblStatus.setText(L.t(t)); lblStatus.setTextColor(cor); }
    }

    // ------------------------------------------------------------------ seleção
    private List<Ftp.Item> marcadosItens() {
        List<Ftp.Item> l = new ArrayList<Ftp.Item>();
        for (Ftp.Item it : itens) if (marcados.contains(it.nome)) l.add(it);
        return l;
    }

    private Ftp.Item um() {
        List<Ftp.Item> m = marcadosItens();
        return m.size() == 1 ? m.get(0) : null;
    }

    private void botoes() {
        if (lista == null) return;
        List<Ftp.Item> m = marcadosItens();
        int n = m.size();
        boolean prot = false;
        for (Ftp.Item it : m) if (Caminhos.protegido(Caminhos.juntar(caminho, it.nome))) prot = true;
        Ftp.Item u = um();
        boolean texto = u != null && !u.pasta && Caminhos.ehTexto(u.nome) && u.tamanho <= Caminhos.LIMITE_EDICAO;
        boolean livre = !ocupado && a.conectado();
        Ui.ativo(bEditar, texto && livre);
        Ui.ativo(bBaixar, n > 0 && livre);
        Ui.ativo(bRenomear, u != null && !prot && livre);
        Ui.ativo(bApagar, n > 0 && !prot && livre);
        bApagar.setText(L.t(n > 1 ? "Apagar (" + n + ")" : "Apagar"));
        bBaixar.setText(L.t(n > 1 ? "Baixar (" + n + ")" : "Baixar"));
        Ui.ativo(bVoltar, !caminho.equals("/"));
        lblSel.setText(L.t(n > 1 ? n + " marcados" : ""));
        btnTudo.setText(L.t(!itens.isEmpty() && n == itens.size() ? "Desmarcar" : "Marcar tudo"));
        if (adaptador != null) adaptador.notifyDataSetChanged();
    }

    private void alternar(int pos) {
        String n = itens.get(pos).nome;
        if (!marcados.remove(n)) marcados.add(n);
        botoes();
    }

    private void marcarTudo() {
        if (marcadosItens().size() == itens.size()) marcados.clear();
        else for (Ftp.Item it : itens) marcados.add(it.nome);
        botoes();
    }

    // ------------------------------------------------------------------ listagem e pesquisa
    private void ir(String c) {
        if (ocupado) return;
        caminho = c;
        fundo = false;
        buscaId++;
        textoBusca = "";
        if (busca != null) busca.setText(L.t(""));
        marcados.clear();
        listar();
    }

    private void listar() {
        if (lista == null) return;
        if (fundo) { buscarFundo(); return; }
        buscaId++;
        lblCaminho.setText(Ftp.legivel(caminho));
        if (!a.conectado()) {
            todos = new ArrayList<Ftp.Item>();
            filtrar(true);
            status("Conecte o PS3 para ver os arquivos.", Ui.AMARELO);
            return;
        }
        status("Carregando…", Ui.CINZA);
        final String c = caminho;
        a.bg(new Runnable() {
            public void run() {
                Ftp f = null;
                try {
                    f = a.conectar();
                    final List<Ftp.Item> l = f.listar(c);
                    a.ui(new Runnable() {
                        public void run() {
                            if (!c.equals(caminho) || fundo) return;
                            todos = l;
                            filtrar(true);
                        }
                    });
                } catch (final IOException e) {
                    a.ui(new Runnable() { public void run() { status("Não consegui abrir esta pasta (" + e.getMessage() + ")", Ui.VERMELHO); } });
                } finally {
                    if (f != null) f.fechar();
                }
            }
        });
    }

    private void filtrar(boolean manter) {
        if (fundo) return;
        String termo = Caminhos.semAcento(textoBusca.trim());
        itens = new ArrayList<Ftp.Item>();
        for (Ftp.Item it : todos)
            if (termo.isEmpty() || Caminhos.semAcento(Ftp.legivel(it.nome)).contains(termo)) itens.add(it);
        Set<String> nomes = new HashSet<String>();
        for (Ftp.Item it : itens) nomes.add(it.nome);
        if (manter) marcados.retainAll(nomes); else marcados.clear();
        botoes();
        if (lista != null) lista.setSelection(0);
        int n = itens.size();
        if (termo.isEmpty()) status(n == 0 ? "Pasta vazia" : n + (n == 1 ? " item" : " itens"), Ui.CINZA);
        else if (n == 0) status("Nada com “" + textoBusca.trim() + "” aqui. Toque em Subpastas para procurar dentro das pastas.", Ui.AMARELO);
        else status(n + " de " + todos.size() + " itens", Ui.CINZA);
    }

    private void limparBusca() {
        boolean estava = fundo;
        fundo = false;
        buscaId++;
        textoBusca = "";
        busca.setText(L.t(""));
        if (estava) listar(); else filtrar(false);
    }

    private void buscarFundo() {
        final String bruto = textoBusca.trim();
        final String termo = Caminhos.semAcento(bruto);
        if (termo.isEmpty()) { status("Digite o nome (ou parte do nome) do que você procura.", Ui.AMARELO); return; }
        if (!a.conectado()) return;
        final int meu = ++buscaId;
        fundo = true;
        btnFundo.setText(L.t("Procurando…"));
        marcados.clear();
        itens = new ArrayList<Ftp.Item>();
        botoes();
        status("Procurando…", Ui.CINZA);
        final String base = caminho;
        a.bg(new Runnable() {
            public void run() {
                Ftp f = null;
                final List<Ftp.Item> achados = new ArrayList<Ftp.Item>();
                String erro = null;
                try {
                    f = a.conectar();
                    List<String> filaP = new ArrayList<String>();
                    filaP.add("");
                    int pastas = 0;
                    long t = 0;
                    while (!filaP.isEmpty() && buscaId == meu && achados.size() < 2000) {
                        String rel = filaP.remove(0);
                        List<Ftp.Item> l;
                        try { l = f.listar(rel.isEmpty() ? base : Caminhos.juntar(base, rel)); }
                        catch (Ftp.Erro e) { continue; }
                        pastas++;
                        for (Ftp.Item it : l) {
                            String r = rel.isEmpty() ? it.nome : rel + "/" + it.nome;
                            if (Caminhos.semAcento(Ftp.legivel(it.nome)).contains(termo)) achados.add(new Ftp.Item(r, it.pasta, it.tamanho));
                            if (it.pasta && (Caminhos.foraDaBusca(base) || !Caminhos.foraDaBusca(Caminhos.juntar(base, r)))) filaP.add(r);
                        }
                        if (System.currentTimeMillis() - t > 300) {
                            t = System.currentTimeMillis();
                            final String m = "Procurando… " + pastas + " pastas vistas, " + achados.size() + " encontrados";
                            a.ui(new Runnable() { public void run() { if (buscaId == meu) status(m, Ui.CINZA); } });
                        }
                    }
                } catch (IOException e) {
                    erro = e.getMessage();
                } finally {
                    if (f != null) f.fechar();
                }
                final String fe = erro;
                a.ui(new Runnable() {
                    public void run() {
                        if (buscaId != meu) return;
                        if (btnFundo != null) btnFundo.setText(L.t("Subpastas"));
                        if (fe != null) { status("Não consegui pesquisar (" + fe + ")", Ui.VERMELHO); return; }
                        itens = achados;
                        botoes();
                        int n = achados.size();
                        if (n == 0) status("Nada com “" + bruto + "” em " + Ftp.legivel(base) + " e nas subpastas.", Ui.AMARELO);
                        else status(n + (n == 1 ? " encontrado" : " encontrados") + " em " + Ftp.legivel(base) + " e nas subpastas", Ui.CINZA);
                    }
                });
            }
        });
    }

    private void abrir(int pos) {
        Ftp.Item it = itens.get(pos);
        if (it.pasta) { ir(Caminhos.juntar(caminho, it.nome)); return; }
        marcados.clear();
        marcados.add(it.nome);
        botoes();
        if (bEditar.isEnabled()) editar();
    }

    // ------------------------------------------------------------------ operações
    interface Trabalho { String fazer(Ftp f) throws IOException; }

    private void operacao(String descricao, final Trabalho t, final boolean recarregar) {
        if (ocupado) return;
        ocupado = true;
        botoes();
        status(descricao, Ui.CINZA);
        a.bg(new Runnable() {
            public void run() {
                Ftp f = null;
                String msg;
                boolean ok;
                try {
                    f = a.conectar();
                    msg = t.fazer(f);
                    ok = true;
                } catch (IOException e) {
                    String m = String.valueOf(e.getMessage());
                    msg = m.contains("protegida") ? "Por segurança, o app não mexe em pastas do sistema." : "Não deu certo: " + m;
                    ok = false;
                } finally {
                    if (f != null) f.fechar();
                }
                final String fm = msg;
                final boolean fok = ok;
                a.ui(new Runnable() {
                    public void run() {
                        ocupado = false;
                        status(fm, fok ? Ui.VERDE : Ui.VERMELHO);
                        botoes();
                        if (fok && recarregar) {
                            a.h.postDelayed(new Runnable() {
                                public void run() {
                                    if (ativo()) { listar(); status(fm, Ui.VERDE); }
                                }
                            }, 500);
                        }
                    }
                });
            }
        });
    }

    private boolean bloquearSistema() {
        if (Caminhos.sistema(caminho)) { status("Por segurança, o app não grava nas pastas do sistema do PS3.", Ui.VERMELHO); return true; }
        if (caminho.equals("/")) { status("Entre no HD (dev_hdd0) ou no pendrive antes de enviar.", Ui.AMARELO); return true; }
        return false;
    }

    private void enviarArquivos() {
        if (!a.conectado() || ocupado || bloquearSistema()) return;
        a.escolherArquivos(new MainActivity.Resultado() {
            public void ok(Intent d) {
                final List<Uri> us = MainActivity.uris(d);
                final String dest = caminho;
                operacao("Enviando…", new Trabalho() {
                    public String fazer(Ftp f) throws IOException {
                        ContentResolver cr = a.getContentResolver();
                        int k = 0;
                        for (Uri u : us) {
                            k++;
                            final int fk = k;
                            a.ui(new Runnable() { public void run() { status("Enviando " + fk + " de " + us.size() + "…", Ui.CINZA); } });
                            InputStream in = cr.openInputStream(u);
                            try { f.enviar(Caminhos.juntar(dest, Ftp.paraFtp(Docs.nome(cr, u))), in, null); } finally { in.close(); }
                        }
                        return us.size() + " arquivo(s) enviados.";
                    }
                }, true);
            }
        });
    }

    private EditText campoTexto(String valor) {
        EditText e = a.campo(valor, "");
        e.setSelectAllOnFocus(true);
        return e;
    }

    private void perguntarNome(String titulo, String valor, final String botao, final Nome r) {
        final EditText e = campoTexto(valor);
        LinearLayout c = Ui.coluna(a);
        c.setPadding(dp(22), dp(8), dp(22), 0);
        c.addView(e);
        a.dialogo().setTitle(titulo).setView(c).setNegativeButton(L.t("Cancelar"), null)
                .setPositiveButton(botao, new DialogInterface.OnClickListener() {
                    public void onClick(DialogInterface d, int w) {
                        String n = e.getText().toString().trim();
                        if (!n.isEmpty() && !n.contains("/")) r.ok(n);
                    }
                }).show();
    }

    interface Nome { void ok(String n); }

    private void novaPasta() {
        if (!a.conectado() || ocupado || bloquearSistema()) return;
        perguntarNome("Nova pasta em " + Ftp.legivel(caminho), "", "Criar", new Nome() {
            public void ok(final String n) {
                final String c = Caminhos.juntar(caminho, Ftp.paraFtp(n));
                operacao("Criando pasta…", new Trabalho() {
                    public String fazer(Ftp f) throws IOException {
                        int cod = f.cmd("MKD " + c);
                        if (cod != 257 && cod != 250) throw new IOException(f.ultimaResposta());
                        return "Pasta “" + n + "” criada.";
                    }
                }, true);
            }
        });
    }

    private void renomear() {
        final Ftp.Item u = um();
        if (u == null) return;
        final String soNome = Caminhos.nome(u.nome);
        perguntarNome("Renomear", Ftp.legivel(soNome), "Renomear", new Nome() {
            public void ok(final String novo) {
                if (novo.equals(Ftp.legivel(soNome))) return;
                final String de = Caminhos.juntar(caminho, u.nome);
                final String para = Caminhos.juntar(Caminhos.pai(de), Ftp.paraFtp(novo));
                String relPai = u.nome.contains("/") ? u.nome.substring(0, u.nome.lastIndexOf('/')) : "";
                marcados.clear();
                marcados.add(relPai.isEmpty() ? Ftp.paraFtp(novo) : relPai + "/" + Ftp.paraFtp(novo));
                operacao("Renomeando…", new Trabalho() {
                    public String fazer(Ftp f) throws IOException { f.renomear(de, para); return "Renomeado para “" + novo + "”."; }
                }, true);
            }
        });
    }

    private void apagar() {
        final List<Ftp.Item> m = marcadosItens();
        if (m.isEmpty() || ocupado) return;
        for (Ftp.Item it : m) if (Caminhos.protegido(Caminhos.juntar(caminho, it.nome))) {
            status("Por segurança, o app não mexe em pastas do sistema.", Ui.VERMELHO);
            return;
        }
        final String base = caminho;
        operacao("Apagando…", new Trabalho() {     // direto, sem caixa de confirmação
            public String fazer(Ftp f) throws IOException {
                int k = 0;
                for (Ftp.Item it : m) {
                    k++;
                    final int fk = k;
                    if (m.size() > 1) a.ui(new Runnable() { public void run() { status("Apagando… " + fk + " de " + m.size(), Ui.CINZA); } });
                    f.apagar(Caminhos.juntar(base, it.nome), it.pasta);
                }
                return m.size() == 1 ? "“" + Ftp.legivel(Caminhos.nome(m.get(0).nome)) + "” foi apagado." : m.size() + " itens apagados.";
            }
        }, true);
    }

    private void baixar() {
        final List<Ftp.Item> m = marcadosItens();
        if (m.isEmpty() || ocupado) return;
        a.escolherPasta(new MainActivity.Resultado() {
            public void ok(Intent d) {
                final Uri arvore = d.getData();
                try {
                    a.getContentResolver().takePersistableUriPermission(arvore,
                            Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
                } catch (Exception ignored) { }
                final String base = caminho;
                operacao("Baixando…", new Trabalho() {
                    public String fazer(Ftp f) throws IOException {
                        long[] cont = {0};
                        for (Ftp.Item it : m)
                            baixarItem(f, arvore, Docs.raiz(arvore), Caminhos.juntar(base, it.nome), it.pasta, cont);
                        return m.size() == 1 ? "Salvo no celular." : m.size() + " itens salvos no celular.";
                    }
                }, false);
            }
        });
    }

    private void baixarItem(Ftp f, Uri arvore, String paiId, String remoto, boolean pasta, final long[] cont) throws IOException {
        ContentResolver cr = a.getContentResolver();
        String nome = Ftp.legivel(Caminhos.nome(remoto));
        if (pasta) {
            String id = Docs.criar(cr, arvore, paiId, DocumentsContract.Document.MIME_TYPE_DIR, nome);
            for (Ftp.Item it : f.listar(remoto)) baixarItem(f, arvore, id, Caminhos.juntar(remoto, it.nome), it.pasta, cont);
        } else {
            String id = Docs.criar(cr, arvore, paiId, "application/octet-stream", nome);
            OutputStream o = Docs.gravar(cr, arvore, id);
            try {
                f.baixar(remoto, o, new Ftp.Progresso() {
                    long t = 0;
                    public void bytes(long n) {
                        cont[0] += n;
                        if (System.currentTimeMillis() - t > 250) {
                            t = System.currentTimeMillis();
                            final String s = "Baixando… " + Caminhos.tamanho(cont[0]);
                            a.ui(new Runnable() { public void run() { status(s, Ui.CINZA); } });
                        }
                    }
                });
            } finally {
                o.close();
            }
        }
    }

    private void editar() {
        final Ftp.Item u = um();
        if (u == null || ocupado) return;
        final String c = Caminhos.juntar(caminho, u.nome);
        status("Abrindo…", Ui.CINZA);
        a.bg(new Runnable() {
            public void run() {
                Ftp f = null;
                try {
                    f = a.conectar();
                    final String texto = f.lerTexto(c);
                    final java.nio.charset.Charset cod = f.codUltimo;
                    a.ui(new Runnable() { public void run() { status("", Ui.CINZA); abrirEditor(c, texto, cod); } });
                } catch (final IOException e) {
                    a.ui(new Runnable() { public void run() { status("Não consegui abrir o arquivo (" + e.getMessage() + ")", Ui.VERMELHO); } });
                } finally {
                    if (f != null) f.fechar();
                }
            }
        });
    }

    private void abrirEditor(final String c, String texto, final java.nio.charset.Charset cod) {
        final boolean leitura = Caminhos.sistema(c);
        LinearLayout box = Ui.coluna(a);
        box.setPadding(dp(16), dp(6), dp(16), 0);
        if (leitura) box.addView(Ui.texto(a, "Arquivo do sistema: aberto só para leitura.", 12, Ui.AMARELO, Ui.NORMAL));
        else if (c.toLowerCase().contains("boot_plugins"))
            box.addView(Ui.texto(a, "Cuidado: uma linha errada aqui pode travar o HEN ao ligar o PS3.", 12, Ui.AMARELO, Ui.NORMAL));
        final EditText e = new EditText(a);
        e.setText(texto);
        e.setTypeface(Typeface.MONOSPACE);
        e.setTextSize(13);
        e.setTextColor(Ui.BRANCO);
        e.setGravity(Gravity.TOP | Gravity.START);
        e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        e.setHorizontallyScrolling(true);
        e.setMinLines(12);
        e.setEnabled(!leitura);
        box.addView(e, Ui.lp(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        android.app.AlertDialog.Builder b = a.dialogo().setTitle(Ftp.legivel(Caminhos.nome(c))).setView(box)
                .setNegativeButton(L.t("Fechar"), null);
        if (!leitura) b.setPositiveButton(L.t("Salvar no PS3"), new DialogInterface.OnClickListener() {
            public void onClick(DialogInterface d, int w) {
                final String novo = e.getText().toString();
                operacao("Salvando no PS3…", new Trabalho() {
                    public String fazer(Ftp f) throws IOException { f.gravarTexto(c, novo, cod); return "Salvo no PS3 ✓"; }
                }, false);
            }
        });
        b.show();
    }

    // ------------------------------------------------------------------ linhas da lista
    private class Adaptador extends BaseAdapter {
        public int getCount() { return itens.size(); }
        public Object getItem(int i) { return itens.get(i); }
        public long getItemId(int i) { return i; }

        public View getView(final int pos, View v, ViewGroup pai) {
            Linha l = v instanceof Linha ? (Linha) v : new Linha();
            l.mostrar(itens.get(pos), pos);
            return l;
        }
    }

    private class Linha extends LinearLayout {
        final CheckBox cb = new CheckBox(a);
        final TextView nome = Ui.texto(a, "", 15, Ui.BRANCO, Ui.NORMAL);
        final TextView onde = Ui.texto(a, "", 11, Ui.CINZA_ESCURO, Ui.NORMAL);
        final TextView tam = Ui.texto(a, "", 12, Ui.CINZA, Ui.NORMAL);
        Ui.Icone ic;
        final LinearLayout iconeBox = new LinearLayout(a);
        String tipoAtual = "";
        int pos;

        Linha() {
            super(a);
            setOrientation(HORIZONTAL);
            setGravity(Gravity.CENTER_VERTICAL);
            setPadding(dp(2), dp(4), dp(12), dp(4));
            setMinimumHeight(dp(52));
            cb.setFocusable(false);                 // senão a linha não recebe o toque
            cb.setFocusableInTouchMode(false);
            addView(cb);
            cb.setOnClickListener(new OnClickListener() { public void onClick(View v) { alternar(pos); } });
            addView(iconeBox, Ui.margem(a, dp(22), dp(22), 0, 0, 10, 0));
            LinearLayout txt = Ui.coluna(a);
            nome.setSingleLine(true);
            nome.setEllipsize(android.text.TextUtils.TruncateAt.MIDDLE);
            onde.setSingleLine(true);
            txt.addView(nome);
            txt.addView(onde);
            addView(txt, Ui.lpPeso(1));
            addView(tam, Ui.margem(a, ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, 8, 0, 0, 0));
        }

        void mostrar(Ftp.Item it, int p) {
            pos = p;
            String tipo = it.pasta ? "pasta" : Caminhos.ehTexto(it.nome) ? "texto" : "arquivo";
            if (!tipo.equals(tipoAtual)) {
                iconeBox.removeAllViews();
                ic = new Ui.Icone(a, tipo, 0xFFE1E8F5);
                iconeBox.addView(ic, Ui.lp(dp(22), dp(22)));
                tipoAtual = tipo;
            }
            int barra = it.nome.lastIndexOf('/');
            nome.setText(Ftp.legivel(barra >= 0 ? it.nome.substring(barra + 1) : it.nome));
            if (barra >= 0) { onde.setVisibility(VISIBLE); onde.setText(L.tm("em {0}", Ftp.legivel(it.nome.substring(0, barra)))); }
            else onde.setVisibility(GONE);
            tam.setText(L.t(it.pasta ? "" : Caminhos.tamanho(it.tamanho)));
            boolean m = marcados.contains(it.nome);
            cb.setChecked(m);
            setBackground(m ? Ui.fundo(a, Ui.LINHA_SEL, 12, 0) : null);
        }
    }
}
