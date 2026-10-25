package com.mrkitanox.pstudo;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.net.wifi.WifiManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.ArrayAdapter;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

/** PSTudo para Android: Enviar jogos, Arquivos, Licenças, Console, Updates e Controle (sem a aba Tela). */
public class MainActivity extends Activity {
    public interface Resultado { void ok(Intent dados); }

    public final Handler h = new Handler(Looper.getMainLooper());
    public SharedPreferences prefs;
    public String estado = "busca";             // busca | ok | erro
    private TextView pillTx;
    private View pillPonto;
    private FrameLayout conteudo;
    private final List<TextView> abasTx = new ArrayList<TextView>();
    private int aba = 0;
    private Resultado esperando;
    private boolean vivo = true;

    public TabEnviar tabEnviar;
    public TabArquivos tabArquivos;
    public TabLicencas tabLicencas;
    public TabConsole tabConsole;
    public TabUpdates tabUpdates;
    public TabControle tabControle;

    // ------------------------------------------------------------------ ciclo de vida
    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        prefs = getSharedPreferences("pstudo", MODE_PRIVATE);
        getWindow().setStatusBarColor(0xFF07142E);
        getWindow().setNavigationBarColor(Ui.FUNDO);
        tabEnviar = new TabEnviar(this);
        tabArquivos = new TabArquivos(this);
        tabLicencas = new TabLicencas(this);
        tabConsole = new TabConsole(this);
        tabUpdates = new TabUpdates(this);
        tabControle = new TabControle(this);

        LinearLayout raiz = Ui.coluna(this);
        GradientDrawable g = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
                new int[]{0xFF0B2149, 0xFF060E20, 0xFF03060E});
        raiz.setBackground(g);

        // topo: nome, status do PS3 e configurações
        LinearLayout topo = Ui.linha(this);
        topo.setPadding(dp(18), dp(14), dp(12), dp(6));
        TextView nome = Ui.texto(this, "PSTudo", 26, Ui.BRANCO, Ui.LEVE);
        topo.addView(nome, Ui.lpPeso(1));
        LinearLayout pill = Ui.linha(this);
        pill.setBackground(Ui.estados(this, 0xE60A1222, Ui.BTN, 18, 0x40FFFFFF));
        pill.setPadding(dp(12), dp(7), dp(14), dp(7));
        pillPonto = new View(this);
        pill.addView(pillPonto, Ui.margem(this, dp(8), dp(8), 0, 0, 8, 0));
        pillTx = Ui.texto(this, "Procurando o PS3…", 13, Ui.BRANCO, Ui.FORTE);
        pill.addView(pillTx);
        pill.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { if (!"ok".equals(estado)) buscar(); }
        });
        topo.addView(pill);
        TextView eng = Ui.botao(this, "⚙", "normal", new View.OnClickListener() {
            public void onClick(View v) { abrirConfig(); }
        });
        eng.setPadding(dp(12), dp(6), dp(12), dp(6));
        eng.setTextSize(18);
        topo.addView(eng, Ui.margem(this, ViewGroup.LayoutParams.WRAP_CONTENT, dp(42), 8, 0, 0, 0));
        raiz.addView(topo);

        conteudo = new FrameLayout(this);
        raiz.addView(conteudo, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));

        // abas embaixo
        LinearLayout nav = Ui.linha(this);
        nav.setBackground(Ui.fundo(this, 0xF00A1222, 24, Ui.BORDA));
        nav.setPadding(dp(5), dp(5), dp(5), dp(5));
        for (int i = 0; i < NOMES_ABAS.length; i++) {
            final int k = i;
            TextView t = Ui.texto(this, NOMES_ABAS[i], 11, Ui.CINZA, Ui.FORTE);
            t.setSingleLine(true);
            t.setGravity(Gravity.CENTER);
            t.setPadding(0, dp(9), 0, dp(9));
            t.setOnClickListener(new View.OnClickListener() {
                public void onClick(View v) { mostrarAba(k); }
            });
            abasTx.add(t);
            nav.addView(t, Ui.lpPeso(1));
        }
        raiz.addView(nav, Ui.margem(this, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 12, 4, 12, 4));
        TextView cred = Ui.texto(this, "Feito por MrKitanoX usando o Claude", 10, Ui.CINZA_ESCURO, Ui.NORMAL);
        cred.setGravity(Gravity.END);
        cred.setPadding(0, 0, dp(16), dp(8));
        raiz.addView(cred, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        setContentView(raiz);

        atualizarStatus("busca");
        mostrarAba(0);
        buscar();
    }

    @Override
    protected void onPause() {
        tabControle.desligar();          // não deixa botão "preso" no PS3 se sair do app
        super.onPause();
    }

    @Override
    public boolean dispatchKeyEvent(android.view.KeyEvent e) {
        if (tabControle != null && tabControle.tecla(e)) return true;
        return super.dispatchKeyEvent(e);
    }

    @Override
    public boolean dispatchGenericMotionEvent(android.view.MotionEvent e) {
        if (tabControle != null && tabControle.movimento(e)) return true;
        return super.dispatchGenericMotionEvent(e);
    }

    @Override
    protected void onDestroy() {
        vivo = false;
        super.onDestroy();
    }

    public int dp(float v) { return Ui.dp(this, v); }

    static final String[] NOMES_ABAS = {"Enviar", "Arquivos", "Licenças", "Console", "Updates", "Controle"};

    // ------------------------------------------------------------------ abas
    public void mostrarAba(int k) {
        if (aba == TabControle.ABA && k != TabControle.ABA) tabControle.desligar();   // solta os botões no PS3
        aba = k;
        for (int i = 0; i < abasTx.size(); i++) {
            TextView t = abasTx.get(i);
            t.setTextColor(i == k ? 0xFF0B1426 : Ui.CINZA);
            t.setBackground(i == k ? Ui.fundo(this, 0xFFF2F5FA, 19, 0) : null);
        }
        conteudo.removeAllViews();
        View v = k == 0 ? tabEnviar.view() : k == 1 ? tabArquivos.view() : k == 2 ? tabLicencas.view()
                : k == 3 ? tabConsole.view() : k == 4 ? tabUpdates.view() : tabControle.view();
        conteudo.addView(v, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
    }

    public int abaAtual() { return aba; }

    public void marcarAba(int k, String texto) {
        abasTx.get(k).setText(texto == null ? NOMES_ABAS[k] : texto);
    }

    // ------------------------------------------------------------------ threads
    public void bg(final Runnable r) {
        new Thread(new Runnable() {
            public void run() {
                try { r.run(); } catch (final RuntimeException e) {
                    ui(new Runnable() { public void run() { aviso("Erro: " + e.getMessage(), true); } });
                }
            }
        }).start();
    }

    public void ui(Runnable r) { if (vivo) h.post(r); }

    public void aviso(String s, boolean longo) {
        Toast.makeText(this, s, longo ? Toast.LENGTH_LONG : Toast.LENGTH_SHORT).show();
    }

    // ------------------------------------------------------------------ conexão
    public String ip() { return prefs.getString("ip", ""); }

    public int porta() { return prefs.getInt("porta", 21); }

    public Ftp conectar() throws IOException {
        Ftp f = new Ftp(ip(), porta());
        f.conectar(prefs.getString("usuario", "anonymous"), prefs.getString("senha", ""));
        return f;
    }

    public void buscar() {
        atualizarStatus("busca");
        final String salvo = ip();
        bg(new Runnable() {
            public void run() {
                final String achou = Rede.procurar(porta(), salvo);
                ui(new Runnable() {
                    public void run() {
                        if (achou != null) {
                            prefs.edit().putString("ip", achou).apply();
                            atualizarStatus("ok");
                            h.postDelayed(checar, 15000);
                        } else {
                            atualizarStatus("erro");
                            h.postDelayed(new Runnable() {
                                public void run() { if ("erro".equals(estado)) buscar(); }
                            }, 15000);
                        }
                    }
                });
            }
        });
    }

    private final Runnable checar = new Runnable() {
        public void run() {
            if (!vivo || !"ok".equals(estado)) return;
            if (tabEnviar.enviando) { h.postDelayed(this, 15000); return; }
            bg(new Runnable() {
                public void run() {
                    final boolean ok = Rede.testarFtp(ip(), porta(), 2500) != null;
                    ui(new Runnable() {
                        public void run() {
                            if (ok) h.postDelayed(checar, 15000);
                            else { atualizarStatus("erro"); h.postDelayed(new Runnable() { public void run() { buscar(); } }, 5000); }
                        }
                    });
                }
            });
        }
    };

    public void atualizarStatus(String e) {
        boolean mudou = !e.equals(estado);
        estado = e;
        int cor = "ok".equals(e) ? Ui.VERDE : "busca".equals(e) ? Ui.AMARELO : Ui.VERMELHO;
        GradientDrawable d = new GradientDrawable();
        d.setShape(GradientDrawable.OVAL);
        d.setColor(cor);
        pillPonto.setBackground(d);
        pillTx.setText("ok".equals(e) ? "PS3 conectado" : "busca".equals(e) ? "Procurando o PS3…" : "PS3 não encontrado");
        if (mudou) {
            tabEnviar.statusMudou();
            tabArquivos.statusMudou();
            tabLicencas.statusMudou();
            tabConsole.statusMudou();
            tabUpdates.statusMudou();
            tabControle.statusMudou();
        }
    }

    public boolean conectado() { return "ok".equals(estado); }

    // ------------------------------------------------------------------ seletor de arquivos do Android
    public void escolher(Intent i, Resultado r) {
        esperando = r;
        try {
            startActivityForResult(i, 77);
        } catch (Exception e) {
            esperando = null;
            aviso("Não encontrei um seletor de arquivos neste aparelho.", true);
        }
    }

    public void escolherPasta(Resultado r) {
        escolher(new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE), r);
    }

    public void escolherArquivos(Resultado r) {
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("*/*");
        i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        escolher(i, r);
    }

    public static List<Uri> uris(Intent d) {
        List<Uri> l = new ArrayList<Uri>();
        if (d == null) return l;
        if (d.getClipData() != null) {
            for (int i = 0; i < d.getClipData().getItemCount(); i++) l.add(d.getClipData().getItemAt(i).getUri());
        } else if (d.getData() != null) l.add(d.getData());
        return l;
    }

    @Override
    protected void onActivityResult(int req, int res, Intent dados) {
        super.onActivityResult(req, res, dados);
        Resultado r = esperando;
        esperando = null;
        if (req == 77 && res == RESULT_OK && r != null && dados != null) {
            if (dados.getData() != null) {
                try { getContentResolver().takePersistableUriPermission(dados.getData(), Intent.FLAG_GRANT_READ_URI_PERMISSION); }
                catch (Exception ignored) { }
            }
            r.ok(dados);
        }
    }

    // ------------------------------------------------------------------ manter acordado durante envios
    private PowerManager.WakeLock wl;
    private WifiManager.WifiLock wifi;

    public void manterAcordado(boolean sim) {
        try {
            if (sim) {
                getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                if (wl == null) {
                    wl = ((PowerManager) getSystemService(Context.POWER_SERVICE))
                            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "PSTudo:envio");
                    wifi = ((WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE))
                            .createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "PSTudo:envio");
                }
                if (!wl.isHeld()) wl.acquire(6 * 3600 * 1000L);
                if (!wifi.isHeld()) wifi.acquire();
            } else {
                getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                if (wl != null && wl.isHeld()) wl.release();
                if (wifi != null && wifi.isHeld()) wifi.release();
            }
        } catch (Exception ignored) { }
    }

    // ------------------------------------------------------------------ configurações
    public AlertDialog.Builder dialogo() {
        return new AlertDialog.Builder(this, android.R.style.Theme_Material_Dialog_Alert);
    }

    public EditText campo(String valor, String dica) {
        EditText e = new EditText(this);
        e.setText(valor);
        e.setHint(dica);
        e.setSingleLine(true);
        e.setTextColor(Ui.BRANCO);
        e.setHintTextColor(Ui.CINZA_ESCURO);
        return e;
    }

    private void abrirConfig() {
        LinearLayout c = Ui.coluna(this);
        c.setPadding(dp(22), dp(8), dp(22), 0);
        TextView dica = Ui.texto(this, "Só mexa aqui se o PS3 não for encontrado sozinho. O IP aparece no PS3 em "
                + "Configurações › Configurações de Rede › Lista de Configurações e Status da Conexão.", 12, Ui.CINZA, Ui.NORMAL);
        c.addView(dica);
        final EditText eIp = campo(ip(), "IP do PS3 (ex.: 192.168.0.20)");
        eIp.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        final EditText eUsr = campo(prefs.getString("usuario", "anonymous"), "Usuário");
        final EditText eSen = campo(prefs.getString("senha", ""), "Senha");
        eSen.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        c.addView(eIp);
        c.addView(eUsr);
        c.addView(eSen);
        TextView td = Ui.texto(this, "Onde salvar no PS3", 13, Ui.CINZA, Ui.NORMAL);
        td.setPadding(0, dp(10), 0, 0);
        c.addView(td);
        final Spinner sp = new Spinner(this);
        sp.setAdapter(new ArrayAdapter<String>(this, android.R.layout.simple_spinner_dropdown_item, Caminhos.DESTINOS));
        String dest = prefs.getString("destino", "Automático");
        for (int i = 0; i < Caminhos.DESTINOS.length; i++) if (Caminhos.DESTINOS[i].equals(dest)) sp.setSelection(i);
        c.addView(sp);
        final CheckBox cbPular = new CheckBox(this);
        cbPular.setText("Não reenviar o que já está no PS3");
        cbPular.setTextColor(Ui.BRANCO);
        cbPular.setChecked(prefs.getBoolean("pular", true));
        c.addView(cbPular);
        final CheckBox cbSom = new CheckBox(this);
        cbSom.setText("Tocar um som quando o envio terminar");
        cbSom.setTextColor(Ui.BRANCO);
        cbSom.setChecked(prefs.getBoolean("som", true));
        c.addView(cbSom);
        dialogo().setTitle("Configurações").setView(c)
                .setPositiveButton("Salvar", new android.content.DialogInterface.OnClickListener() {
                    public void onClick(android.content.DialogInterface d, int w) {
                        prefs.edit().putString("ip", eIp.getText().toString().trim())
                                .putString("usuario", eUsr.getText().toString().trim().isEmpty() ? "anonymous" : eUsr.getText().toString().trim())
                                .putString("senha", eSen.getText().toString())
                                .putString("destino", (String) sp.getSelectedItem())
                                .putBoolean("pular", cbPular.isChecked())
                                .putBoolean("som", cbSom.isChecked()).apply();
                        buscar();
                    }
                })
                .setNeutralButton("Procurar de novo", new android.content.DialogInterface.OnClickListener() {
                    public void onClick(android.content.DialogInterface d, int w) {
                        prefs.edit().putString("ip", "").apply();
                        buscar();
                    }
                })
                .setNegativeButton("Fechar", null).show();
    }
}
