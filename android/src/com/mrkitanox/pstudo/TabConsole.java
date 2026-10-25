package com.mrkitanox.pstudo;

import android.content.Intent;
import android.hardware.input.InputManager;
import android.net.Uri;
import android.view.Gravity;
import android.view.InputDevice;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.CheckBox;
import android.widget.CompoundButton;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.Spinner;
import android.widget.Switch;
import android.widget.TextView;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** Aba Console: energia, XPAD Revolution (instalar, ligar sozinho, analógico, controles, desinstalar) e plugins. */
public class TabConsole {
    private final MainActivity a;
    private boolean ocupado = false;
    private boolean registro = false;        // mostrando a tela de controles
    // dados lidos do PS3
    private List<String> sprx = new ArrayList<String>();
    private Map<String, Integer> ativos = null;
    private boolean xpad = false, auto = false, lido = false;
    private int[] analog = null;
    private final Map<String, Integer> sessao = new HashMap<String, Integer>();
    private String msg = "";
    private int msgCor = Ui.CINZA;

    private TextView lblMsg, lblXpad, bDesinstalar, bInstalar, bZip, bAnalog, bControles, bReiniciar, bDesligar;
    private Switch swAuto;
    private SeekBar sbSat, sbDz;
    private TextView vSat, vDz;
    private LinearLayout listaPlugins;
    private boolean mexendoSwitch = false;

    TabConsole(MainActivity a) { this.a = a; }

    private int dp(float v) { return a.dp(v); }

    private boolean ativa() { return a.abaAtual() == 3 && lblMsg != null; }

    void statusMudou() {
        if (a.abaAtual() == 3 && !registro) a.mostrarAba(3);
    }

    private void msg(String t, int cor) {
        msg = t;
        msgCor = cor;
        if (lblMsg != null) { lblMsg.setText(t); lblMsg.setTextColor(cor); }
    }

    View view() {
        if (registro) return telaControles();
        ScrollView sv = new ScrollView(a);
        LinearLayout c = Ui.coluna(a);
        c.setPadding(dp(14), dp(6), dp(14), dp(12));

        // ---- energia
        LinearLayout en = Ui.cartao(a);
        en.addView(Ui.titulo(a, "Energia"));
        LinearLayout le = Ui.linha(a);
        bReiniciar = Ui.botao(a, "↻  Reiniciar", "normal", new View.OnClickListener() {
            public void onClick(View v) { energia(true); }
        });
        bDesligar = Ui.botao(a, "⏻  Desligar", "perigo", new View.OnClickListener() {
            public void onClick(View v) { energia(false); }
        });
        le.addView(bReiniciar, Ui.lpPeso(1));
        le.addView(Ui.espaco(a, 1), Ui.lp(dp(10), 1));
        le.addView(bDesligar, Ui.lpPeso(1));
        en.addView(le, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 10, 0, 0));
        c.addView(en, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 0, 0, 10));

        // ---- XPAD
        LinearLayout ct = Ui.cartao(a);
        ct.addView(Ui.titulo(a, "Suporte a controles"));
        ct.addView(Ui.texto(a, "XPAD Revolution: Xbox, GameSir, 8BitDo, DS4 e outros.", 12, Ui.CINZA, Ui.NORMAL));
        LinearLayout ls = Ui.linha(a);
        lblXpad = Ui.texto(a, lido ? (xpad ? "✓ Instalado" + (ativos != null && ativos.containsKey(Xpad.VSH) ? " e ativo agora" : "") : "Não instalado") : "Verificando…",
                12, xpad ? Ui.VERDE : Ui.CINZA, Ui.NORMAL);
        ls.addView(lblXpad, Ui.lpPeso(1));
        bDesinstalar = Ui.texto(a, "Desinstalar", 12, Ui.VERMELHO, Ui.FORTE);
        bDesinstalar.setPadding(dp(8), dp(8), dp(2), dp(8));
        bDesinstalar.setOnClickListener(new View.OnClickListener() { public void onClick(View v) { desinstalar(); } });
        ls.addView(bDesinstalar);
        ct.addView(ls, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 6, 0, 2));
        LinearLayout lb = Ui.linha(a);
        bInstalar = Ui.botao(a, xpad ? "Atualizar e ativar" : "Instalar e ativar", "azul", new View.OnClickListener() {
            public void onClick(View v) { instalar(null); }
        });
        bZip = Ui.botao(a, "Usar ZIP", "normal", new View.OnClickListener() {
            public void onClick(View v) {
                a.escolherArquivos(new MainActivity.Resultado() {
                    public void ok(Intent d) { List<Uri> u = MainActivity.uris(d); if (!u.isEmpty()) instalar(u.get(0)); }
                });
            }
        });
        lb.addView(bInstalar, Ui.lpPeso(1.4f));
        lb.addView(Ui.espaco(a, 1), Ui.lp(dp(10), 1));
        lb.addView(bZip, Ui.lpPeso(1));
        ct.addView(lb);
        swAuto = new Switch(a);
        swAuto.setText("Ligar sozinho " + Xpad.ATRASO + " s depois do HEN");
        swAuto.setTextColor(Ui.BRANCO);
        swAuto.setTextSize(13);
        swAuto.setChecked(lido ? auto : a.prefs.getBoolean("xpad_auto", true));
        swAuto.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
            public void onCheckedChanged(CompoundButton b, boolean on) { if (!mexendoSwitch) alternarAuto(on); }
        });
        ct.addView(swAuto, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 8, 0, 4));
        vSat = new TextView(a);
        vDz = new TextView(a);
        sbSat = slider(ct, "Alcance do analógico", 70, 100, analog != null ? analog[0] : 80, vSat, true);
        sbDz = slider(ct, "Zona morta", 0, 10, analog != null ? analog[1] : 4, vDz, false);
        LinearLayout l3 = Ui.linha(a);
        bAnalog = Ui.botao(a, "Salvar analógico", "normal", new View.OnClickListener() {
            public void onClick(View v) { salvarAnalog(); }
        });
        bControles = Ui.botao(a, "Controles", "normal", new View.OnClickListener() {
            public void onClick(View v) { registro = true; a.mostrarAba(3); }
        });
        l3.addView(bAnalog, Ui.lpPeso(1));
        l3.addView(Ui.espaco(a, 1), Ui.lp(dp(10), 1));
        l3.addView(bControles, Ui.lpPeso(1));
        ct.addView(l3, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 10, 0, 0));
        c.addView(ct, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 0, 0, 10));

        // ---- plugins
        LinearLayout pl = Ui.cartao(a);
        pl.addView(Ui.titulo(a, "Plugins — só até reiniciar"));
        pl.addView(Ui.texto(a, "Ative um plugin agora. Ao reiniciar o PS3 tudo volta ao normal.", 12, Ui.CINZA, Ui.NORMAL));
        listaPlugins = Ui.coluna(a);
        pl.addView(listaPlugins, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 8, 0, 0));
        LinearLayout rod = Ui.linha(a);
        lblMsg = Ui.texto(a, msg, 12, msgCor, Ui.NORMAL);
        rod.addView(lblMsg, Ui.lpPeso(1));
        rod.addView(Ui.botao(a, "⟳ Atualizar", "normal", new View.OnClickListener() {
            public void onClick(View v) { carregar(); }
        }), Ui.margem(a, ViewGroup.LayoutParams.WRAP_CONTENT, dp(40), 8, 0, 0, 0));
        pl.addView(rod, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 8, 0, 0));
        c.addView(pl);

        sv.addView(c);
        desenharPlugins();
        botoes();
        if (!lido) carregar();
        return sv;
    }

    private SeekBar slider(LinearLayout pai, String rotulo, final int de, int ate, int valor, final TextView val, final boolean sat) {
        LinearLayout t = Ui.linha(a);
        t.addView(Ui.texto(a, rotulo, 13, Ui.BRANCO, Ui.NORMAL), Ui.lpPeso(1));
        val.setTextColor(Ui.CINZA);
        val.setTextSize(13);
        t.addView(val);
        pai.addView(t, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 8, 0, 0));
        SeekBar s = new SeekBar(a);
        s.setMax(ate - de);
        s.setProgress(Math.max(0, Math.min(ate - de, valor - de)));
        SeekBar.OnSeekBarChangeListener l = new SeekBar.OnSeekBarChangeListener() {
            public void onProgressChanged(SeekBar b, int p, boolean u) {
                int v = p + de;
                val.setText(sat ? v + (v == 80 ? "  (parecido com DS3)" : v == 100 ? "  (sem correção)" : "") : v + "%");
            }
            public void onStartTrackingTouch(SeekBar b) { }
            public void onStopTrackingTouch(SeekBar b) { }
        };
        s.setOnSeekBarChangeListener(l);
        l.onProgressChanged(s, s.getProgress(), false);
        pai.addView(s);
        return s;
    }

    private void botoes() {
        if (lblMsg == null) return;
        boolean on = a.conectado() && !ocupado;
        Ui.ativo(bReiniciar, on && !a.tabEnviar.enviando);
        Ui.ativo(bDesligar, on && !a.tabEnviar.enviando);
        Ui.ativo(bInstalar, on && lido);
        Ui.ativo(bZip, on && lido);
        Ui.ativo(bDesinstalar, on && xpad);
        Ui.ativo(swAuto, on && xpad);
        Ui.ativo(bControles, on && xpad);
        Ui.ativo(bAnalog, on && analog != null);
        Ui.ativo(sbSat, on && analog != null);
        Ui.ativo(sbDz, on && analog != null);
    }

    private static String trava(String c) {
        String l = c.toLowerCase(Locale.ROOT);
        if (l.contains("webftp_server") || l.contains("webman")) return "Necessário para este app (webMAN)";
        if (l.endsWith("xpad_game.sprx")) return "Carrega dentro do jogo com SELECT + L3 + R3";
        return null;
    }

    private void desenharPlugins() {
        if (listaPlugins == null) return;
        listaPlugins.removeAllViews();
        Map<String, Integer> at = ativos != null ? ativos : sessao;
        List<String> todos = new ArrayList<String>(at.keySet());
        for (String s : sprx) if (!todos.contains(s)) todos.add(s);
        if (todos.isEmpty()) {
            listaPlugins.addView(Ui.texto(a, lido ? "Nenhum plugin encontrado em /dev_hdd0/plugins." : "Lendo o console…",
                    12, Ui.CINZA, Ui.NORMAL));
            return;
        }
        for (final String p : todos) {
            final boolean ligado = at.containsKey(p);
            final String tv = trava(p);
            LinearLayout l = Ui.linha(a);
            l.setBackground(Ui.fundo(a, 0xFF0B1426, 10, 0));
            l.setPadding(dp(12), dp(8), dp(8), dp(8));
            LinearLayout t = Ui.coluna(a);
            LinearLayout t1 = Ui.linha(a);
            TextView n = Ui.texto(a, Ftp.legivel(Caminhos.nome(p)), 13, Ui.BRANCO, Ui.FORTE);
            n.setSingleLine(true);
            t1.addView(n);
            if (ligado) t1.addView(Ui.texto(a, "  ● ativo", 11, Ui.VERDE, Ui.NORMAL));
            t.addView(t1);
            TextView sub = Ui.texto(a, tv != null ? tv : Ftp.legivel(p), 11, tv != null ? Ui.AMARELO : Ui.CINZA_ESCURO, Ui.NORMAL);
            sub.setSingleLine(true);
            sub.setEllipsize(android.text.TextUtils.TruncateAt.START);
            t.addView(sub);
            l.addView(t, Ui.lpPeso(1));
            TextView b = Ui.botao(a, ligado ? "Desativar" : "Ativar", tv != null ? "normal" : ligado ? "perigo" : "azul",
                    new View.OnClickListener() { public void onClick(View v) { alternarPlugin(p, !ligado); } });
            b.setTextSize(13);
            l.addView(b, Ui.margem(a, dp(100), dp(38), 8, 0, 0, 0));
            Ui.ativo(b, a.conectado() && !ocupado && tv == null);
            listaPlugins.addView(l, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 0, 0, 6));
        }
    }

    // ------------------------------------------------------------------ leitura
    void carregar() {
        if (!a.conectado()) { msg("Conecte o PS3 para ver os plugins.", Ui.AMARELO); return; }
        msg("Lendo o console…", Ui.CINZA);
        final String ip = a.ip();
        a.bg(new Runnable() {
            public void run() {
                Ftp f = null;
                final List<String> s = new ArrayList<String>();
                boolean x = false, au = false;
                int[] an = null;
                String erro = null;
                try {
                    f = a.conectar();
                    try {
                        for (Ftp.Item it : f.listar("/dev_hdd0/plugins")) {
                            String c = Caminhos.juntar("/dev_hdd0/plugins", it.nome);
                            if (it.pasta) {
                                try {
                                    for (Ftp.Item i2 : f.listar(c))
                                        if (!i2.pasta && i2.nome.toLowerCase(Locale.ROOT).endsWith(".sprx")) s.add(Caminhos.juntar(c, i2.nome));
                                } catch (IOException ignored) { }
                            } else if (it.nome.toLowerCase(Locale.ROOT).endsWith(".sprx")) s.add(c);
                        }
                    } catch (IOException ignored) { }
                    x = f.existe(Xpad.VSH);
                    au = Xpad.inicioLigado(f);
                    an = Xpad.lerAnalog(f);
                } catch (IOException e) {
                    erro = e.getMessage();
                } finally {
                    if (f != null) f.fechar();
                }
                final Map<String, Integer> at = WebMan.pluginsAtivos(ip);
                final boolean fx = x, fau = au;
                final int[] fan = an;
                final String fe = erro;
                a.ui(new Runnable() {
                    public void run() {
                        if (fe != null) { msg("Não consegui ler o console (" + fe + ")", Ui.VERMELHO); return; }
                        sprx = s;
                        ativos = at;
                        xpad = fx;
                        auto = fau;
                        analog = fan;
                        lido = true;
                        String pendente = msgPendente;
                        msgPendente = null;
                        if (a.abaAtual() == 3 && !registro) {
                            a.mostrarAba(3);
                            if (pendente != null) msg(pendente, Ui.VERDE);
                            else {
                                int on = 0;
                                Map<String, Integer> m = at != null ? at : sessao;
                                on = m.size();
                                msg(s.size() + " plugin(s) • " + on + " ativo(s)" + (at == null ? "  (o PS3 não informa quais estão ativos)" : ""), Ui.CINZA);
                            }
                        }
                    }
                });
            }
        });
    }

    private String msgPendente = null;

    // ------------------------------------------------------------------ ações
    interface Acao { String fazer() throws IOException; }
    private int geracao = 0;

    private void rodar(String descricao, final Acao ac, final boolean recarregar) {
        if (ocupado) return;
        ocupado = true;
        final int g = ++geracao;
        botoes();
        desenharPlugins();
        msg(descricao, Ui.CINZA);
        // se o PS3 travar no meio, os botões não podem ficar cinza para sempre
        a.h.postDelayed(new Runnable() {
            public void run() {
                if (!ocupado || geracao != g) return;
                ocupado = false;
                if (ativa()) {
                    msg("O PS3 está demorando para responder. Toque em ⟳ Atualizar para conferir.", Ui.AMARELO);
                    botoes();
                    desenharPlugins();
                }
            }
        }, 75000);
        a.bg(new Runnable() {
            public void run() {
                String m;
                boolean ok;
                try {
                    m = ac.fazer();
                    ok = true;
                } catch (IOException e) {
                    m = "Não deu certo: " + e.getMessage();
                    ok = false;
                } catch (Throwable e) {          // qualquer outro erro também libera os botões
                    m = "Não deu certo: " + e;
                    ok = false;
                }
                final String fm = m;
                final boolean fok = ok;
                a.ui(new Runnable() {
                    public void run() {
                        if (geracao != g) return;    // já começou outra ação depois desta
                        ocupado = false;
                        if (fok && recarregar) { msgPendente = fm; carregar(); }
                        if (ativa()) { msg(fm, fok ? Ui.VERDE : Ui.VERMELHO); botoes(); desenharPlugins(); }
                    }
                });
            }
        });
    }

    private void energia(final boolean reiniciar) {
        final String ip = a.ip();
        rodar(reiniciar ? "Reiniciando o PS3…" : "Desligando o PS3…", new Acao() {
            public String fazer() throws IOException {
                WebMan.energia(ip, reiniciar);
                return reiniciar ? "Reiniciando o PS3… depois é só ativar o HEN de novo." : "PS3 desligando…";
            }
        }, false);
        sessao.clear();
        a.h.postDelayed(new Runnable() { public void run() { a.atualizarStatus(reiniciar ? "busca" : "erro"); } }, 1500);
        if (reiniciar) a.h.postDelayed(new Runnable() { public void run() { a.buscar(); } }, 45000);
    }

    private void alternarPlugin(final String p, final boolean ligar) {
        final String ip = a.ip();
        final Map<String, Integer> ocup = ativos;
        final String nome = Ftp.legivel(Caminhos.nome(p));
        rodar(ligar ? "Ativando " + nome + "… alguns plugins levam até meio minuto" : "Desativando " + nome + "…", new Acao() {
            public String fazer() throws IOException {
                if (ligar) sessao.put(p, WebMan.ativar(ip, p, ocup));
                else {
                    Integer slot = ocup != null && ocup.containsKey(p) ? ocup.get(p) : sessao.get(p);
                    WebMan.desativar(ip, p, slot);
                    sessao.remove(p);
                }
                WebMan.popup(ip, "PSTudo: " + nome + (ligar ? " ativado" : " desativado"));
                try { Thread.sleep(1500); } catch (InterruptedException ignored) { }
                return nome + (ligar ? " ativado até reiniciar." : " desativado.");
            }
        }, true);
    }

    private File pastaBackup() {
        File base = a.getExternalFilesDir(null);
        if (base == null) base = a.getFilesDir();
        return new File(base, "backup_xpad/" + new SimpleDateFormat("yyyy-MM-dd_HH-mm-ss", Locale.ROOT).format(new Date()));
    }

    private void instalar(final Uri zipLocal) {
        final String ip = a.ip();
        final boolean querAuto = a.prefs.getBoolean("xpad_auto", true);
        final Map<String, Integer> ocup = ativos;
        lblXpad.setText(zipLocal == null ? "Baixando o XPAD Revolution…" : "Lendo o ZIP…");
        rodar("Instalando o XPAD…", new Acao() {
            public String fazer() throws IOException {
                byte[] zip;
                if (zipLocal != null) {
                    InputStream in = a.getContentResolver().openInputStream(zipLocal);
                    ByteArrayOutputStream b = new ByteArrayOutputStream();
                    byte[] buf = new byte[65536];
                    int n;
                    while ((n = in.read(buf)) > 0) b.write(buf, 0, n);
                    in.close();
                    zip = b.toByteArray();
                } else {
                    try { zip = Xpad.baixarZip(); }
                    catch (IOException e) { throw new IOException("sem acesso ao GitHub. Baixe o ZIP no navegador e use “Usar ZIP”."); }
                }
                Xpad.Pacote p = Xpad.abrirZip(zip);
                Ftp f = a.conectar();
                List<String> mantidos;
                boolean ligouAuto = false;
                try {
                    mantidos = Xpad.instalar(f, p);
                    if (querAuto) { Xpad.ligarInicio(f, pastaBackup()); ligouAuto = true; }
                } finally {
                    f.fechar();
                }
                boolean ativo = ocup != null && ocup.containsKey(Xpad.VSH);
                if (!ativo) {
                    try { sessao.put(Xpad.VSH, WebMan.ativar(ip, Xpad.VSH, ocup)); ativo = true; } catch (IOException ignored) { }
                }
                String nome = p.versao.isEmpty() ? "XPAD Revolution" : p.versao;
                String t = ativo ? nome + " instalado e ativo. Conecte o controle quando aparecer “XPAD Rev Loaded!”."
                        : nome + " instalado. Não consegui ativar agora: use Ativar na lista de plugins.";
                if (ligouAuto) t += " Nos próximos boots ele liga sozinho " + Xpad.ATRASO + " s depois do HEN.";
                if (!mantidos.isEmpty()) t += " Configurações antigas mantidas.";
                return t;
            }
        }, true);
    }

    private void alternarAuto(final boolean ligar) {
        a.prefs.edit().putBoolean("xpad_auto", ligar).apply();
        if (!a.conectado() || ocupado) return;
        rodar("Salvando…", new Acao() {
            public String fazer() throws IOException {
                Ftp f = a.conectar();
                try {
                    if (ligar) {
                        int n = Xpad.ligarInicio(f, pastaBackup());
                        return "Pronto: nos próximos boots o XPAD liga sozinho " + Xpad.ATRASO + " s depois do HEN."
                                + (n > 0 ? " Ele saiu do boot_plugins.txt para não carregar duas vezes." : "");
                    }
                    Xpad.desligarInicio(f);
                    return "Pronto: o XPAD não liga mais sozinho. Use Ativar quando quiser.";
                } finally {
                    f.fechar();
                }
            }
        }, true);
    }

    private void salvarAnalog() {
        final int sat = sbSat.getProgress() + 70, dz = sbDz.getProgress();
        rodar("Salvando ajustes…", new Acao() {
            public String fazer() throws IOException {
                Ftp f = a.conectar();
                try { Xpad.gravarAnalog(f, sat, dz); } finally { f.fechar(); }
                return "✓ Analógico salvo. Desative e ative o XPAD para aplicar.";
            }
        }, true);
    }

    private void desinstalar() {
        final String ip = a.ip();
        final Map<String, Integer> at = ativos;
        rodar("Desinstalando o XPAD…", new Acao() {      // direto, sem caixa de confirmação
            public String fazer() throws IOException {
                Map<String, Integer> todos = new LinkedHashMap<String, Integer>();
                if (at != null) todos.putAll(at);
                for (Map.Entry<String, Integer> e : sessao.entrySet()) if (!todos.containsKey(e.getKey())) todos.put(e.getKey(), e.getValue());
                for (Map.Entry<String, Integer> e : todos.entrySet()) {
                    if (Xpad.ehXpad(e.getKey())) {
                        try { WebMan.desativar(ip, e.getKey(), e.getValue()); } catch (IOException ignored) { }
                        sessao.remove(e.getKey());
                    }
                }
                File bk = pastaBackup();
                Ftp f = a.conectar();
                int[] r;
                try { r = Xpad.desinstalar(f, bk); } finally { f.fechar(); }
                String t = "XPAD desinstalado: " + r[0] + " arquivo(s)";
                if (r[1] > 0) t += " e " + r[1] + " linha(s) do boot";
                if (r[2] > 0) t += ", início automático desligado";
                String[] copia = bk.list();
                if (copia != null && copia.length > 0) t += ". Configurações salvas em Android/data/com.mrkitanox.pstudo/files/backup_xpad";
                return t + ".";
            }
        }, true);
    }

    // ------------------------------------------------------------------ controles (registrados x disponíveis)
    private List<Xpad.Controle> registrados = null;
    private java.util.Set<String> carregados = null;     // "vid:pid" que o XPAD registrou no último boot (xpad.log)
    private boolean logCheio = false;

    private View telaControles() {
        ScrollView sv = new ScrollView(a);
        LinearLayout c = Ui.coluna(a);
        c.setPadding(dp(14), dp(4), dp(14), dp(12));
        LinearLayout topo = Ui.linha(a);
        topo.addView(Ui.botao(a, "←", "normal", new View.OnClickListener() {
            public void onClick(View v) { registro = false; a.mostrarAba(3); }
        }), Ui.lp(dp(48), dp(40)));
        TextView t = Ui.texto(a, "Controles do XPAD", 20, Ui.BRANCO, Ui.LEVE);
        t.setPadding(dp(12), 0, 0, 0);
        topo.addView(t, Ui.lpPeso(1));
        c.addView(topo);
        c.addView(Ui.texto(a, "Já registrados: o que está no xpad_devices.txt do PS3. Disponíveis: controles ligados neste "
                + "celular (cabo OTG ou Bluetooth) que ainda não foram registrados.", 12, Ui.CINZA, Ui.NORMAL),
                Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 6, 0, 10));

        boolean largo = a.getResources().getConfiguration().screenWidthDp >= 600;
        LinearLayout colunas = largo ? Ui.linha(a) : Ui.coluna(a);
        colunas.setGravity(Gravity.TOP);
        final LinearLayout esq = Ui.cartao(a), dir = Ui.cartao(a);
        if (largo) {
            colunas.addView(esq, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
            colunas.addView(Ui.espaco(a, 1), Ui.lp(dp(10), 1));
            colunas.addView(dir, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        } else {
            colunas.addView(esq, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 0, 0, 10));
            colunas.addView(dir, Ui.lp(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        }
        c.addView(colunas);
        final TextView status = Ui.texto(a, "", 12, Ui.CINZA, Ui.NORMAL);
        c.addView(status, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 10, 0, 6));
        LinearLayout bts = Ui.linha(a);
        final TextView bReativar = Ui.botao(a, "Reativar XPAD", "normal", new View.OnClickListener() {
            public void onClick(View v) { reativarXpad(status); }
        });
        bts.addView(bReativar, Ui.lpPeso(1));
        c.addView(bts);
        sv.addView(c);
        preencherControles(esq, dir, status);
        return sv;
    }

    private static String[] tipo(int vid, int pid) {
        if (vid == 0x054C && (pid == 0x05C4 || pid == 0x09CC || pid == 0x0BA0)) return new String[]{"PTYPE_PS4", null};
        if (vid == 0x054C && (pid == 0x0CE6 || pid == 0x0DF2)) return new String[]{"PTYPE_PS5", null};
        if (vid == 0x045E && (pid == 0x0291 || pid == 0x0719)) return new String[]{"XTYPE_XBOX360W", null};
        int[] one = {0x02D1, 0x02DD, 0x02E3, 0x02EA, 0x0B00, 0x0B12, 0x0B13, 0x0B20, 0x0B22};
        if (vid == 0x045E) for (int o : one) if (pid == o) return new String[]{null, "Controle de Xbox One/Series ainda não é suportado pelo XPAD."};
        return new String[]{"XTYPE_XBOX360", null};
    }

    /** Controles ligados no celular (gamepads/joysticks com VID/PID). */
    private List<Object[]> controlesDoCelular() {
        List<Object[]> l = new ArrayList<Object[]>();
        java.util.Set<String> vistos = new java.util.HashSet<String>();
        for (int id : InputDevice.getDeviceIds()) {
            InputDevice d = InputDevice.getDevice(id);
            if (d == null || d.isVirtual()) continue;
            int s = d.getSources();
            // só controles de verdade: precisa ter analógico (joystick). Sensores de digital, botões do
            // aparelho etc. às vezes se dizem "gamepad" (ex.: uinput-goodix) e não podem entrar na lista.
            boolean joystick = (s & InputDevice.SOURCE_JOYSTICK) == InputDevice.SOURCE_JOYSTICK
                    && d.getMotionRange(android.view.MotionEvent.AXIS_X) != null;
            String nm = String.valueOf(d.getName()).toLowerCase(Locale.ROOT);
            boolean interno = nm.startsWith("uinput") || nm.contains("fingerprint") || nm.contains("goodix")
                    || nm.contains("fpc") || nm.contains("gpio") || nm.contains("pwrkey") || nm.contains("touch");
            if (!joystick || interno || d.getVendorId() == 0) continue;
            String k = d.getVendorId() + ":" + d.getProductId();
            if (!vistos.add(k)) continue;
            l.add(new Object[]{d.getVendorId(), d.getProductId(), d.getName()});
        }
        return l;
    }

    private void preencherControles(final LinearLayout esq, final LinearLayout dir, final TextView status) {
        esq.removeAllViews();
        dir.removeAllViews();
        esq.addView(Ui.titulo(a, "Já registrados no PS3"));
        dir.addView(Ui.titulo(a, "Disponíveis neste celular"));
        if (registrados == null) {
            esq.addView(Ui.texto(a, "Lendo o PS3…", 12, Ui.CINZA, Ui.NORMAL));
            a.bg(new Runnable() {
                public void run() {
                    Ftp f = null;
                    List<Xpad.Controle> l = new ArrayList<Xpad.Controle>();
                    java.util.Set<String> carr = null;
                    boolean cheio = false;
                    try {
                        f = a.conectar();
                        l = Xpad.registrados(f.lerTextoOuVazio(Xpad.DEVICES));
                        String log = f.lerTextoOuVazio(Xpad.DIR + "/xpad.log");
                        if (!log.isEmpty()) { carr = Xpad.carregadosNoLog(log); cheio = log.contains("LDD table full"); }
                    }
                    catch (IOException ignored) { }
                    finally { if (f != null) f.fechar(); }
                    final List<Xpad.Controle> fl = l;
                    final java.util.Set<String> fc = carr;
                    final boolean fch = cheio;
                    a.ui(new Runnable() { public void run() { registrados = fl; carregados = fc; logCheio = fch; preencherControles(esq, dir, status); } });
                }
            });
            return;
        }
        TextView cont = Ui.texto(a, registrados.size() + " de " + Xpad.LIMITE_DEVICES, 11, Ui.CINZA_ESCURO, Ui.NORMAL);
        esq.addView(cont);
        if (registrados.isEmpty()) esq.addView(Ui.texto(a, "Nenhum controle registrado ainda.", 12, Ui.CINZA, Ui.NORMAL));
        java.util.Set<String> ja = new java.util.HashSet<String>();
        boolean algumFora = false;
        for (final Xpad.Controle r : registrados) {
            ja.add(r.chave());
            LinearLayout l = Ui.linha(a);
            l.setBackground(Ui.fundo(a, 0xFF0B1426, 10, 0));
            l.setPadding(dp(12), dp(8), dp(8), dp(8));
            LinearLayout t = Ui.coluna(a);
            t.addView(Ui.texto(a, r.nome, 13, Ui.BRANCO, Ui.FORTE));
            t.addView(Ui.texto(a, String.format(Locale.ROOT, "%04X:%04X  •  %s", r.vid, r.pid, Xpad.nomeTipo(r.tipo)), 11, Ui.CINZA_ESCURO, Ui.NORMAL));
            if (carregados != null) {
                boolean ok = carregados.contains(r.chave());
                if (ok || logCheio) t.addView(Ui.texto(a, ok ? "✓ carregado no último boot"
                        : "✗ não carregou: o PS3 ficou sem espaço (limite do XPAD)", 11, ok ? Ui.VERDE : Ui.AMARELO, Ui.NORMAL));
                if (!ok && logCheio) algumFora = true;
            }
            l.addView(t, Ui.lpPeso(1));
            TextView b = Ui.botao(a, "Remover", "perigo", new View.OnClickListener() {
                public void onClick(View v) {
                    status.setText("Removendo " + r.nome + "…");
                    a.bg(new Runnable() {
                        public void run() {
                            String m;
                            Ftp f = null;
                            try { f = a.conectar(); Xpad.remover(f, r); m = r.nome + " removido. Reative o XPAD (ou reinicie o PS3) para valer."; }
                            catch (IOException e) { m = "Não consegui remover (" + e.getMessage() + ")"; }
                            finally { if (f != null) f.fechar(); }
                            final String fm = m;
                            a.ui(new Runnable() { public void run() { status.setText(fm); registrados = null; preencherControles(esq, dir, status); } });
                        }
                    });
                }
            });
            b.setTextSize(12);
            l.addView(b, Ui.margem(a, ViewGroup.LayoutParams.WRAP_CONTENT, dp(34), 8, 0, 0, 0));
            esq.addView(l, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 6, 0, 0));
        }

        if (algumFora) esq.addView(Ui.texto(a, "O XPAD carrega a lista dele primeiro e o PS3 só tem uns 22 espaços, então "
                + "controles registrados aqui podem ficar de fora. Use um modo do controle que o XPAD já conhece "
                + "(ex.: DualShock 4, luz azul nos GameSir).", 11, Ui.CINZA, Ui.NORMAL),
                Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 8, 0, 0));
        final List<Object[]> marcados = new ArrayList<Object[]>();
        int novos = 0;
        for (final Object[] d : controlesDoCelular()) {
            int vid = (Integer) d[0], pid = (Integer) d[1];
            if (ja.contains(vid + ":" + pid)) continue;
            novos++;
            final String[] tp = tipo(vid, pid);
            LinearLayout l = Ui.coluna(a);
            l.setBackground(Ui.fundo(a, 0xFF0B1426, 10, 0));
            l.setPadding(dp(8), dp(6), dp(8), dp(8));
            final CheckBox cb = new CheckBox(a);
            cb.setText((String) d[2]);
            cb.setTextColor(Ui.BRANCO);
            cb.setChecked(tp[0] != null);
            cb.setEnabled(tp[0] != null);
            l.addView(cb);
            l.addView(Ui.texto(a, String.format(Locale.ROOT, "%04X:%04X", vid, pid) + (tp[1] != null ? "  •  " + tp[1] : ""), 11,
                    tp[1] != null ? Ui.AMARELO : Ui.CINZA_ESCURO, Ui.NORMAL));
            final Spinner sp = new Spinner(a);
            String[] nomes = new String[Xpad.TIPOS.length];
            int sel = 0;
            for (int i = 0; i < nomes.length; i++) { nomes[i] = Xpad.TIPOS[i][1]; if (Xpad.TIPOS[i][0].equals(tp[0])) sel = i; }
            sp.setAdapter(new ArrayAdapter<String>(a, android.R.layout.simple_spinner_dropdown_item, nomes));
            sp.setSelection(sel);
            if (tp[0] != null) l.addView(sp);
            marcados.add(new Object[]{d, cb, sp, tp[0]});
            dir.addView(l, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 6, 0, 0));
        }
        if (novos == 0) dir.addView(Ui.texto(a, "Nenhum controle novo. Ligue o controle no celular (cabo OTG ou Bluetooth) "
                + "e toque em Procurar de novo.", 12, Ui.CINZA, Ui.NORMAL));
        LinearLayout bts = Ui.linha(a);
        bts.addView(Ui.botao(a, "Procurar de novo", "normal", new View.OnClickListener() {
            public void onClick(View v) { preencherControles(esq, dir, status); }
        }), Ui.lpPeso(1));
        if (novos > 0) {
            bts.addView(Ui.espaco(a, 1), Ui.lp(dp(8), 1));
            bts.addView(Ui.botao(a, "Registrar →", "azul", new View.OnClickListener() {
                public void onClick(View v) {
                    final List<Xpad.Controle> esc = new ArrayList<Xpad.Controle>();
                    for (Object[] m : marcados) {
                        CheckBox cb = (CheckBox) m[1];
                        if (!cb.isChecked() || m[3] == null) continue;
                        Object[] d = (Object[]) m[0];
                        String t = Xpad.TIPOS[((Spinner) m[2]).getSelectedItemPosition()][0];
                        esc.add(new Xpad.Controle((Integer) d[0], (Integer) d[1], (String) d[2], t));
                    }
                    if (esc.isEmpty()) { status.setText("Marque pelo menos um controle."); return; }
                    status.setText("Gravando no PS3…");
                    a.bg(new Runnable() {
                        public void run() {
                            String m;
                            Ftp f = null;
                            try {
                                f = a.conectar();
                                int[] r = Xpad.registrar(f, esc);
                                m = r[0] + " registrado(s)" + (r[1] > 0 ? ", " + r[1] + " já estava(m) na lista" : "")
                                        + (r[2] > 0 ? ", " + r[2] + " sem espaço (limite de " + Xpad.LIMITE_DEVICES + ")" : "") + "."
                                        + (r[0] > 0 ? " Reative o XPAD (ou reinicie o PS3) para o controle ser reconhecido." : "");
                            } catch (IOException e) {
                                m = "Não consegui gravar (" + e.getMessage() + ")";
                            } finally {
                                if (f != null) f.fechar();
                            }
                            final String fm = m;
                            a.ui(new Runnable() { public void run() { status.setText(fm); registrados = null; preencherControles(esq, dir, status); } });
                        }
                    });
                }
            }), Ui.lpPeso(1));
        }
        dir.addView(bts, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 10, 0, 0));
    }

    private void reativarXpad(final TextView status) {
        final String ip = a.ip();
        status.setText("Reativando o XPAD…");
        a.bg(new Runnable() {
            public void run() {
                String m;
                try {
                    Map<String, Integer> at = WebMan.pluginsAtivos(ip);
                    Integer slot = at != null && at.containsKey(Xpad.VSH) ? at.get(Xpad.VSH) : sessao.get(Xpad.VSH);
                    if ((at != null && at.containsKey(Xpad.VSH)) || sessao.containsKey(Xpad.VSH)) {
                        WebMan.desativar(ip, Xpad.VSH, slot);
                        Thread.sleep(1500);
                        at = WebMan.pluginsAtivos(ip);
                    }
                    sessao.put(Xpad.VSH, WebMan.ativar(ip, Xpad.VSH, at));
                    m = "XPAD reativado. Espere a mensagem no PS3 e conecte o controle.";
                } catch (Exception e) {
                    m = "Não consegui reativar (" + e.getMessage() + ")";
                }
                final String fm = m;
                a.ui(new Runnable() { public void run() { status.setText(fm); lido = false; } });
            }
        });
    }
}
