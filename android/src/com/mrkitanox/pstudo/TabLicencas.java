package com.mrkitanox.pstudo;

import android.content.Intent;
import android.net.Uri;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** Aba Licenças: manda arquivos .rap direto para /dev_hdd0/exdata. */
public class TabLicencas {
    static class Rap { Uri uri; String nome; boolean valido; }

    private final MainActivity a;
    private final List<Rap> raps = new ArrayList<Rap>();
    private TextView status, btnEnviar;
    private String noPs3 = "";
    private boolean ocupado = false;

    TabLicencas(MainActivity a) { this.a = a; }

    private int dp(float v) { return a.dp(v); }

    void statusMudou() { if (btnEnviar != null) Ui.ativo(btnEnviar, pode()); }

    private boolean pode() {
        if (!a.conectado() || ocupado) return false;
        for (Rap r : raps) if (r.valido) return true;
        return false;
    }

    View view() {
        LinearLayout c = Ui.coluna(a);
        c.setPadding(dp(16), dp(12), dp(16), dp(12));
        TextView t = Ui.texto(a, raps.isEmpty() ? "Licenças (RAP)" : "Pronto para enviar", 24, Ui.BRANCO, Ui.LEVE);
        t.setGravity(Gravity.CENTER);
        c.addView(t, Ui.lp(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        int validos = 0;
        for (Rap r : raps) if (r.valido) validos++;
        TextView s = Ui.texto(a, raps.isEmpty() ? "Os arquivos .rap vão direto para a pasta exdata do console."
                : validos + (validos == 1 ? " licença" : " licenças") + " → /dev_hdd0/exdata", 14, Ui.CINZA, Ui.NORMAL);
        s.setGravity(Gravity.CENTER);
        c.addView(s, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 4, 0, 14));
        if (raps.isEmpty()) {
            LinearLayout card = Ui.coluna(a);
            card.setGravity(Gravity.CENTER);
            card.setBackground(Ui.estados(a, 0xFF0E1A33, Ui.BTN_PRESS, 20, Ui.BORDA));
            card.setPadding(dp(16), dp(30), dp(16), dp(30));
            card.addView(new Ui.Icone(a, "arquivo", Ui.BRANCO), Ui.lp(dp(52), dp(52)));
            TextView ct = Ui.texto(a, "Escolher arquivos .rap", 18, Ui.BRANCO, Ui.FORTE);
            ct.setPadding(0, dp(10), 0, dp(2));
            card.addView(ct);
            card.addView(Ui.texto(a, "Pode escolher vários de uma vez", 13, Ui.CINZA, Ui.NORMAL));
            card.setClickable(true);
            card.setOnClickListener(new View.OnClickListener() { public void onClick(View v) { escolher(); } });
            c.addView(card, Ui.lp(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
            c.addView(Ui.espaco(a, 1), new LinearLayout.LayoutParams(1, 0, 1));
        } else {
            ScrollView sv = new ScrollView(a);
            LinearLayout lista = Ui.coluna(a);
            for (int k = 0; k < raps.size(); k++) {
                final int ki = k;
                Rap r = raps.get(k);
                LinearLayout l = Ui.linha(a);
                l.setBackground(Ui.fundo(a, 0x0DFFFFFF, 14, Ui.BORDA));
                l.setPadding(dp(14), dp(10), dp(8), dp(10));
                TextView n = Ui.texto(a, r.nome, 14, r.valido ? Ui.BRANCO : Ui.CINZA_ESCURO, Ui.NORMAL);
                n.setSingleLine(true);
                l.addView(n, Ui.lpPeso(1));
                if (!r.valido) l.addView(Ui.texto(a, "inválido", 12, Ui.AMARELO, Ui.NORMAL));
                TextView x = Ui.texto(a, "✕", 16, Ui.CINZA, Ui.NORMAL);
                x.setPadding(dp(14), dp(4), dp(10), dp(4));
                x.setOnClickListener(new View.OnClickListener() {
                    public void onClick(View v) { raps.remove(ki); a.mostrarAba(2); }
                });
                l.addView(x);
                lista.addView(l, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 0, 0, 6));
            }
            sv.addView(lista);
            c.addView(sv, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
            LinearLayout b = Ui.linha(a);
            b.addView(Ui.botao(a, "+ Mais", "contorno", new View.OnClickListener() {
                public void onClick(View v) { escolher(); }
            }), Ui.lpPeso(1));
            b.addView(Ui.espaco(a, 1), Ui.lp(dp(8), 1));
            b.addView(Ui.botao(a, "Limpar", "contorno", new View.OnClickListener() {
                public void onClick(View v) { raps.clear(); a.mostrarAba(2); }
            }), Ui.lpPeso(1));
            c.addView(b, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 8, 0, 8));
            btnEnviar = Ui.botao(a, "Enviar para o PS3", "azul", new View.OnClickListener() {
                public void onClick(View v) { enviar(); }
            });
            btnEnviar.setMinHeight(dp(50));
            c.addView(btnEnviar, Ui.lp(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
            Ui.ativo(btnEnviar, pode());
        }
        status = Ui.texto(a, noPs3, 12, Ui.CINZA, Ui.NORMAL);
        status.setGravity(Gravity.CENTER);
        c.addView(status, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 8, 0, 0));
        contarNoPs3();
        return c;
    }

    private void contarNoPs3() {
        if (!a.conectado()) return;
        a.bg(new Runnable() {
            public void run() {
                Ftp f = null;
                try {
                    f = a.conectar();
                    int n = 0;
                    for (Ftp.Item it : f.listar("/dev_hdd0/exdata"))
                        if (!it.pasta && it.nome.toLowerCase(Locale.ROOT).endsWith(".rap")) n++;
                    final String t = "Já existem " + n + (n == 1 ? " licença" : " licenças") + " na pasta exdata";
                    a.ui(new Runnable() { public void run() { noPs3 = t; if (status != null) status.setText(t); } });
                } catch (IOException ignored) {
                } finally {
                    if (f != null) f.fechar();
                }
            }
        });
    }

    private void escolher() {
        a.escolherArquivos(new MainActivity.Resultado() {
            public void ok(Intent d) {
                for (Uri u : MainActivity.uris(d)) {
                    Rap r = new Rap();
                    r.uri = u;
                    r.nome = Docs.nome(a.getContentResolver(), u);
                    r.valido = r.nome.toLowerCase(Locale.ROOT).endsWith(".rap") && Docs.tamanho(a.getContentResolver(), u) == 16;
                    boolean repetido = false;
                    for (Rap x : raps) if (x.nome.equalsIgnoreCase(r.nome)) repetido = true;
                    if (!repetido) raps.add(r);
                }
                a.mostrarAba(2);
            }
        });
    }

    private void enviar() {
        if (!pode()) return;
        ocupado = true;
        Ui.ativo(btnEnviar, false);
        btnEnviar.setText("Enviando…");
        final List<Rap> lista = new ArrayList<Rap>();
        for (Rap r : raps) if (r.valido) lista.add(r);
        a.bg(new Runnable() {
            public void run() {
                Ftp f = null;
                String msg;
                boolean ok = false;
                try {
                    f = a.conectar();
                    f.criarPasta("/dev_hdd0/exdata");
                    for (Rap r : lista) {
                        InputStream in = a.getContentResolver().openInputStream(r.uri);
                        try { f.enviar("/dev_hdd0/exdata/" + Ftp.paraFtp(r.nome), in, null); } finally { in.close(); }
                    }
                    msg = lista.size() + (lista.size() == 1 ? " licença copiada" : " licenças copiadas") + " para a pasta exdata.";
                    ok = true;
                } catch (IOException e) {
                    msg = "Não deu certo: " + e.getMessage();
                } finally {
                    if (f != null) f.fechar();
                }
                final String m = msg;
                final boolean fok = ok;
                a.ui(new Runnable() {
                    public void run() {
                        ocupado = false;
                        if (fok) raps.clear();
                        a.aviso(m, true);
                        if (a.abaAtual() == 2) a.mostrarAba(2);
                    }
                });
            }
        });
    }
}
