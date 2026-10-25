package com.mrkitanox.pstudo;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.view.MotionEvent;
import android.view.View;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Controle de PS3 desenhado na tela, com vários dedos ao mesmo tempo. */
public class PadView extends View {
    public interface Ouvinte { void mudou(Set<String> botoes, Set<String> dpad, float lx, float ly, float rx, float ry); }

    private static class Botao {
        final String id, rotulo;
        final int cor;
        final boolean redondo;
        float x, y, r, w, h;
        Botao(String id, String rotulo, int cor, boolean redondo) { this.id = id; this.rotulo = rotulo; this.cor = cor; this.redondo = redondo; }
        boolean dentro(float px, float py, float folga) {
            if (redondo) return Math.hypot(px - x, py - y) <= r * folga;
            return Math.abs(px - x) <= w / 2 * folga && Math.abs(py - y) <= h / 2 * folga;
        }
    }

    private static class Stick { float cx, cy, R, vx, vy; }

    private final List<Botao> botoes = new ArrayList<Botao>();
    private final Stick esq = new Stick(), dir = new Stick();
    private final Map<Integer, Object> dedos = new HashMap<Integer, Object>();   // id do dedo -> Botao ou Stick
    private final Set<String> apertados = new HashSet<String>();
    private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF rr = new RectF();
    private Ouvinte ouvinte;
    private boolean ligado = true;

    public PadView(Context c) {
        super(c);
        String[][] defs = {
                {"L2", "L2"}, {"L1", "L1"}, {"R1", "R1"}, {"R2", "R2"},
                {"up", "▲"}, {"down", "▼"}, {"left", "◀"}, {"right", "▶"},
                {"triangle", "△"}, {"circle", "○"}, {"cross", "✕"}, {"square", "□"},
                {"select", "SELECT"}, {"start", "START"}, {"psbtn", "PS"}, {"L3", "L3"}, {"R3", "R3"}};
        for (String[] d : defs) {
            int cor = d[0].equals("triangle") ? 0xFF4ADE80 : d[0].equals("circle") ? 0xFFF87171
                    : d[0].equals("cross") ? 0xFF7FB2F0 : d[0].equals("square") ? 0xFFF0A0D8 : Ui.BRANCO;
            boolean redondo = !(d[0].startsWith("L") || d[0].startsWith("R") || d[0].equals("select") || d[0].equals("start"));
            botoes.add(new Botao(d[0], d[1], cor, redondo));
        }
    }

    public void setOuvinte(Ouvinte o) { ouvinte = o; }

    public void setLigado(boolean on) { ligado = on; if (!on) soltarTudo(); invalidate(); }

    public void soltarTudo() {
        dedos.clear();
        apertados.clear();
        esq.vx = esq.vy = dir.vx = dir.vy = 0;
        avisar();
        invalidate();
    }

    private Botao b(String id) { for (Botao x : botoes) if (x.id.equals(id)) return x; return null; }

    @Override
    protected void onSizeChanged(int w, int h, int ow, int oh) {
        float m = Math.min(w, h);
        boolean deitado = w > h * 1.2f;
        float br = m * (deitado ? 0.085f : 0.075f);           // raio dos botões redondos
        float topo = h * 0.09f, sw = m * 0.17f, sh = m * 0.085f;
        float[][] ombros = {{0.09f, 0}, {0.27f, 0}, {0.73f, 0}, {0.91f, 0}};
        String[] ids = {"L2", "L1", "R1", "R2"};
        for (int i = 0; i < 4; i++) {
            Botao x = b(ids[i]);
            x.x = w * ombros[i][0]; x.y = topo; x.w = sw; x.h = sh;
        }
        float cy = deitado ? h * 0.42f : h * 0.36f;
        float dx = w * (deitado ? 0.17f : 0.24f), fx = w - dx, dist = br * 1.55f;
        posicao("up", dx, cy - dist, br); posicao("down", dx, cy + dist, br);
        posicao("left", dx - dist, cy, br); posicao("right", dx + dist, cy, br);
        posicao("triangle", fx, cy - dist, br); posicao("cross", fx, cy + dist, br);
        posicao("square", fx - dist, cy, br); posicao("circle", fx + dist, cy, br);
        Botao s = b("select"), st = b("start");
        s.x = w * 0.40f; st.x = w * 0.60f; s.y = st.y = deitado ? h * 0.25f : cy - dist * 1.6f;
        s.w = st.w = m * 0.16f; s.h = st.h = m * 0.07f;
        posicao("psbtn", w * 0.5f, deitado ? h * 0.42f : cy + dist * 0.2f, br * 0.8f);
        float sy = deitado ? h * 0.76f : h * 0.72f, R = m * (deitado ? 0.15f : 0.16f);
        esq.cx = deitado ? w * 0.36f : w * 0.27f; dir.cx = w - esq.cx; esq.cy = dir.cy = sy; esq.R = dir.R = R;
        Botao l3 = b("L3"), r3 = b("R3");
        l3.w = r3.w = m * 0.12f; l3.h = r3.h = m * 0.07f;
        if (deitado) {             // deitado não cabe embaixo: L3/R3 ficam do lado de fora dos analógicos
            l3.y = r3.y = sy + R * 0.55f;
            l3.x = esq.cx - R - l3.w * 0.75f;
            r3.x = dir.cx + R + r3.w * 0.75f;
        } else {
            l3.y = r3.y = Math.min(h - l3.h, sy + R + m * 0.07f);
            l3.x = esq.cx; r3.x = dir.cx;
        }
    }

    private void posicao(String id, float x, float y, float r) { Botao q = b(id); q.x = x; q.y = y; q.r = r; }

    @Override
    protected void onDraw(Canvas c) {
        p.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        p.setTextAlign(Paint.Align.CENTER);
        for (Stick s : new Stick[]{esq, dir}) {
            p.setStyle(Paint.Style.FILL);
            p.setColor(0x22FFFFFF);
            c.drawCircle(s.cx, s.cy, s.R, p);
            p.setStyle(Paint.Style.STROKE);
            p.setStrokeWidth(Math.max(2, s.R * 0.02f));
            p.setColor(0x40FFFFFF);
            c.drawCircle(s.cx, s.cy, s.R, p);
            boolean ativo = s.vx != 0 || s.vy != 0;
            p.setStyle(Paint.Style.FILL);
            p.setColor(ativo ? Ui.AZUL_PRESS : 0xFF2A3A5E);
            c.drawCircle(s.cx + s.vx * s.R * 0.6f, s.cy + s.vy * s.R * 0.6f, s.R * 0.42f, p);
        }
        for (Botao x : botoes) {
            boolean on = apertados.contains(x.id);
            p.setStyle(Paint.Style.FILL);
            p.setColor(on ? Ui.AZUL : 0xFF16233F);
            if (x.redondo) c.drawCircle(x.x, x.y, x.r, p);
            else {
                rr.set(x.x - x.w / 2, x.y - x.h / 2, x.x + x.w / 2, x.y + x.h / 2);
                c.drawRoundRect(rr, x.h / 2, x.h / 2, p);
            }
            p.setColor(on ? Ui.BRANCO : x.cor);
            float tam = x.redondo ? x.r * (x.rotulo.length() > 1 ? 0.7f : 1.0f) : x.h * (x.rotulo.length() > 3 ? 0.36f : 0.5f);
            p.setTextSize(tam);
            float base = x.y - (p.descent() + p.ascent()) / 2;
            c.drawText(x.rotulo, x.x, base, p);
        }
        if (!ligado) c.drawColor(0x99050B18);
    }

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        if (!ligado) return true;
        int acao = e.getActionMasked();
        if (acao == MotionEvent.ACTION_DOWN || acao == MotionEvent.ACTION_POINTER_DOWN) {
            int i = e.getActionIndex();
            pegar(e.getPointerId(i), e.getX(i), e.getY(i));
        } else if (acao == MotionEvent.ACTION_MOVE) {
            for (int i = 0; i < e.getPointerCount(); i++) mover(e.getPointerId(i), e.getX(i), e.getY(i));
        } else if (acao == MotionEvent.ACTION_UP || acao == MotionEvent.ACTION_POINTER_UP) {
            soltar(e.getPointerId(e.getActionIndex()));
        } else if (acao == MotionEvent.ACTION_CANCEL) {
            soltarTudo();
            return true;
        }
        recalcular();
        return true;
    }

    private void pegar(int id, float x, float y) {
        for (Stick s : new Stick[]{esq, dir}) {
            if (Math.hypot(x - s.cx, y - s.cy) <= s.R * 1.25f) { dedos.put(id, s); mexer(s, x, y); return; }
        }
        Botao q = achar(x, y);
        if (q != null) dedos.put(id, q);
    }

    private Botao achar(float x, float y) {
        Botao melhor = null;
        double md = Double.MAX_VALUE;
        for (Botao q : botoes) {
            if (!q.dentro(x, y, 1.3f)) continue;
            double d = Math.hypot(x - q.x, y - q.y);
            if (d < md) { md = d; melhor = q; }
        }
        return melhor;
    }

    private void mover(int id, float x, float y) {
        Object o = dedos.get(id);
        if (o instanceof Stick) mexer((Stick) o, x, y);
        else if (o instanceof Botao) {               // dá para escorregar o dedo de um botão para outro
            Botao q = achar(x, y);
            if (q != null && q != o) dedos.put(id, q);
        }
    }

    private void mexer(Stick s, float x, float y) {
        float vx = (x - s.cx) / s.R, vy = (y - s.cy) / s.R;
        float n = (float) Math.hypot(vx, vy);
        if (n > 1) { vx /= n; vy /= n; }
        s.vx = vx; s.vy = vy;
    }

    private void soltar(int id) {
        Object o = dedos.remove(id);
        if (o instanceof Stick) { ((Stick) o).vx = 0; ((Stick) o).vy = 0; }
    }

    private void recalcular() {
        Set<String> novos = new HashSet<String>();
        for (Object o : dedos.values()) if (o instanceof Botao) novos.add(((Botao) o).id);
        apertados.clear();
        apertados.addAll(novos);
        avisar();
        invalidate();
    }

    private void avisar() {
        if (ouvinte == null) return;
        Set<String> bt = new HashSet<String>(), dp = new HashSet<String>();
        for (String s : apertados) {
            if (s.equals("up") || s.equals("down") || s.equals("left") || s.equals("right")) dp.add(s); else bt.add(s);
        }
        ouvinte.mudou(bt, dp, esq.vx, esq.vy, dir.vx, dir.vy);
    }
}
