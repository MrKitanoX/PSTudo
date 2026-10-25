package com.mrkitanox.pstudo;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.text.TextUtils;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Cores e peças de interface (tudo em código, no estilo do PSTudo do PC). */
public final class Ui {
    private Ui() { }

    public static final int FUNDO = 0xFF050B18;
    public static final int PAINEL = 0xFF0A1222;
    public static final int CARD = 0xFF0F1A30;
    public static final int LINHA_SEL = 0xFF12305C;
    public static final int BTN = 0xFF16233F;
    public static final int BTN_PRESS = 0xFF20345C;
    public static final int AZUL = 0xFF0070D1;
    public static final int AZUL_PRESS = 0xFF1888F0;
    public static final int PERIGO = 0xFF3A1620;
    public static final int PERIGO_PRESS = 0xFF5A1E2C;
    public static final int PERIGO_TXT = 0xFFFCA5A5;
    public static final int BRANCO = 0xFFFFFFFF;
    public static final int CINZA = 0xFF9AA4B8;
    public static final int CINZA_ESCURO = 0xFF5D6679;
    public static final int VERDE = 0xFF34D399;
    public static final int AMARELO = 0xFFFBBF24;
    public static final int VERMELHO = 0xFFF87171;
    public static final int BORDA = 0x30FFFFFF;

    public static final Typeface LEVE = Typeface.create("sans-serif-light", Typeface.NORMAL);
    public static final Typeface NORMAL = Typeface.create("sans-serif", Typeface.NORMAL);
    public static final Typeface FORTE = Typeface.create("sans-serif-medium", Typeface.NORMAL);

    public static int dp(Context c, float v) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, c.getResources().getDisplayMetrics()));
    }

    public static GradientDrawable fundo(Context c, int cor, float raioDp, int borda) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(cor);
        g.setCornerRadius(dp(c, raioDp));
        if (borda != 0) g.setStroke(Math.max(1, dp(c, 1)), borda);
        return g;
    }

    public static Drawable estados(Context c, int cor, int corPress, float raioDp, int borda) {
        StateListDrawable s = new StateListDrawable();
        s.addState(new int[]{android.R.attr.state_pressed}, fundo(c, corPress, raioDp, borda));
        s.addState(new int[]{}, fundo(c, cor, raioDp, borda));
        return s;
    }

    public static TextView texto(Context c, String s, float sp, int cor, Typeface tf) {
        TextView t = new TextView(c);
        t.setText(s);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setTextColor(cor);
        t.setTypeface(tf);
        return t;
    }

    public static TextView titulo(Context c, String s) { return texto(c, s, 16, BRANCO, FORTE); }

    /** Botão arredondado. estilo: "normal", "azul", "perigo", "contorno". */
    public static TextView botao(Context c, String s, String estilo, View.OnClickListener l) {
        TextView b = texto(c, s, 14, BRANCO, FORTE);
        b.setGravity(Gravity.CENTER);
        b.setSingleLine(true);
        b.setEllipsize(TextUtils.TruncateAt.END);
        b.setPadding(dp(c, 16), dp(c, 10), dp(c, 16), dp(c, 10));
        b.setMinHeight(dp(c, 42));
        if ("azul".equals(estilo)) b.setBackground(estados(c, AZUL, AZUL_PRESS, 21, 0));
        else if ("perigo".equals(estilo)) {
            b.setBackground(estados(c, PERIGO, PERIGO_PRESS, 21, 0));
            b.setTextColor(PERIGO_TXT);
        } else if ("contorno".equals(estilo)) b.setBackground(estados(c, 0x00000000, BTN, 21, 0x60FFFFFF));
        else b.setBackground(estados(c, BTN, BTN_PRESS, 21, 0));
        b.setClickable(true);
        b.setFocusable(true);
        b.setOnClickListener(l);
        return b;
    }

    public static void ativo(View v, boolean on) {
        v.setEnabled(on);
        v.setAlpha(on ? 1f : 0.4f);
    }

    public static LinearLayout coluna(Context c) {
        LinearLayout l = new LinearLayout(c);
        l.setOrientation(LinearLayout.VERTICAL);
        return l;
    }

    public static LinearLayout linha(Context c) {
        LinearLayout l = new LinearLayout(c);
        l.setOrientation(LinearLayout.HORIZONTAL);
        l.setGravity(Gravity.CENTER_VERTICAL);
        return l;
    }

    public static LinearLayout cartao(Context c) {
        LinearLayout l = coluna(c);
        l.setBackground(fundo(c, CARD, 14, 0));
        l.setPadding(dp(c, 16), dp(c, 14), dp(c, 16), dp(c, 14));
        return l;
    }

    public static LinearLayout.LayoutParams lp(int w, int h) { return new LinearLayout.LayoutParams(w, h); }

    public static LinearLayout.LayoutParams lpPeso(float peso) {
        return new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, peso);
    }

    public static LinearLayout.LayoutParams margem(Context c, int w, int h, float e, float t, float d, float b) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(w, h);
        p.setMargins(dp(c, e), dp(c, t), dp(c, d), dp(c, b));
        return p;
    }

    public static View espaco(Context c, float dpAlt) {
        View v = new View(c);
        v.setLayoutParams(new LinearLayout.LayoutParams(1, dp(c, dpAlt)));
        return v;
    }

    /** Barra de progresso arredondada. */
    public static class Barra extends View {
        private float frac = 0;
        private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final RectF r = new RectF();

        public Barra(Context c) { super(c); }

        public void set(float f) { frac = Math.max(0, Math.min(1, f)); invalidate(); }

        @Override
        protected void onDraw(Canvas cv) {
            float h = getHeight(), w = getWidth(), raio = h / 2;
            r.set(0, 0, w, h);
            p.setColor(0x1CFFFFFF);
            cv.drawRoundRect(r, raio, raio, p);
            r.set(0, 0, Math.max(h, w * frac), h);
            p.setColor(AZUL);
            cv.drawRoundRect(r, raio, raio, p);
        }
    }

    /** Ícone simples desenhado (pasta, arquivo, texto, disco, check, alerta). */
    public static class Icone extends View {
        private final String tipo;
        private int cor;
        private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);

        public Icone(Context c, String tipo, int cor) {
            super(c);
            this.tipo = tipo;
            this.cor = cor;
            p.setStyle(Paint.Style.STROKE);
            p.setStrokeJoin(Paint.Join.ROUND);
            p.setStrokeCap(Paint.Cap.ROUND);
        }

        public void setCor(int c) { cor = c; invalidate(); }

        @Override
        protected void onDraw(Canvas cv) {
            float w = getWidth(), h = getHeight(), s = Math.min(w, h), x0 = (w - s) / 2, y0 = (h - s) / 2;
            p.setColor(cor);
            p.setStrokeWidth(Math.max(2f, s * 0.075f));
            RectF r = new RectF();
            if ("pasta".equals(tipo)) {
                r.set(x0 + s * .1f, y0 + s * .28f, x0 + s * .9f, y0 + s * .82f);
                cv.drawRoundRect(r, s * .08f, s * .08f, p);
                r.set(x0 + s * .1f, y0 + s * .18f, x0 + s * .45f, y0 + s * .32f);
                cv.drawRoundRect(r, s * .05f, s * .05f, p);
            } else if ("disco".equals(tipo)) {
                cv.drawCircle(x0 + s / 2, y0 + s / 2, s * .4f, p);
                cv.drawCircle(x0 + s / 2, y0 + s / 2, s * .1f, p);
            } else if ("check".equals(tipo) || "alerta".equals(tipo)) {
                cv.drawCircle(x0 + s / 2, y0 + s / 2, s * .44f, p);
                if ("check".equals(tipo)) {
                    cv.drawLine(x0 + s * .3f, y0 + s * .52f, x0 + s * .45f, y0 + s * .66f, p);
                    cv.drawLine(x0 + s * .45f, y0 + s * .66f, x0 + s * .72f, y0 + s * .36f, p);
                } else {
                    cv.drawLine(x0 + s / 2, y0 + s * .28f, x0 + s / 2, y0 + s * .56f, p);
                    cv.drawPoint(x0 + s / 2, y0 + s * .70f, p);
                }
            } else {
                android.graphics.Path pa = new android.graphics.Path();
                pa.moveTo(x0 + s * .22f, y0 + s * .1f);
                pa.lineTo(x0 + s * .62f, y0 + s * .1f);
                pa.lineTo(x0 + s * .8f, y0 + s * .28f);
                pa.lineTo(x0 + s * .8f, y0 + s * .9f);
                pa.lineTo(x0 + s * .22f, y0 + s * .9f);
                pa.close();
                cv.drawPath(pa, p);
                if ("texto".equals(tipo)) {
                    for (float y : new float[]{.42f, .57f, .72f})
                        cv.drawLine(x0 + s * .35f, y0 + s * y, x0 + s * .66f, y0 + s * y, p);
                }
            }
        }
    }

    public static int cor(String hex) { return Color.parseColor(hex); }
}
