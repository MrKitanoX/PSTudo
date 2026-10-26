package com.mrkitanox.pstudo;

import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.CompoundButton;
import android.widget.LinearLayout;
import android.widget.Switch;
import android.widget.TextView;

import java.util.HashSet;
import java.util.Set;

/** Aba Controle: controla o PS3 pelo celular (na tela ou com um controle Bluetooth/USB ligado no celular). */
public class TabControle {
    static final int ABA = 5;

    private final MainActivity a;
    private Remoto remoto = null;
    private PadView pad;
    private Switch sw;
    private TextView lblMsg;

    // controle físico ligado no celular
    private final Set<String> fisBotoes = new HashSet<String>(), fisDpad = new HashSet<String>();
    private float fLx, fLy, fRx, fRy;
    // controle da tela
    private Set<String> telaBotoes = new HashSet<String>(), telaDpad = new HashSet<String>();
    private float tLx, tLy, tRx, tRy;

    TabControle(MainActivity a) { this.a = a; }

    private int dp(float v) { return a.dp(v); }

    boolean ligado() { return remoto != null; }

    View view() {
        LinearLayout c = Ui.coluna(a);
        c.setPadding(dp(14), dp(4), dp(14), dp(6));
        LinearLayout topo = Ui.linha(a);
        topo.addView(Ui.texto(a, "Controle remoto", 20, Ui.BRANCO, Ui.LEVE), Ui.lpPeso(1));
        sw = new Switch(a);
        sw.setText("Ligado  ");
        sw.setTextColor(Ui.BRANCO);
        sw.setTextSize(14);
        sw.setChecked(ligado());
        sw.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
            public void onCheckedChanged(CompoundButton b, boolean on) { if (on) ligar(); else desligar(); }
        });
        topo.addView(sw);
        c.addView(topo);
        lblMsg = Ui.texto(a, "", 12, Ui.CINZA, Ui.NORMAL);
        c.addView(lblMsg, Ui.margem(a, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 0, 2, 0, 4));
        pad = new PadView(a);
        pad.setLigado(ligado());
        pad.setOuvinte(new PadView.Ouvinte() {
            public void mudou(Set<String> bt, Set<String> dpad, float lx, float ly, float rx, float ry) {
                telaBotoes = bt; telaDpad = dpad; tLx = lx; tLy = ly; tRx = rx; tRy = ry;
                mandar();
            }
        });
        c.addView(pad, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        msgPadrao();
        return c;
    }

    private void msgPadrao() {
        if (lblMsg == null) return;
        if (!a.conectado()) { lblMsg.setText("Conecte o PS3 para usar o controle remoto."); lblMsg.setTextColor(Ui.AMARELO); return; }
        lblMsg.setTextColor(Ui.CINZA);
        lblMsg.setText(ligado() ? "Para jogos: desligue os outros controles do PS3 antes de ligar aqui (senão este vira o jogador 2). "
                + "Também aceita um controle Bluetooth ligado no celular. O analógico vai inclinado até o fim."
                : "Ligue para controlar o PS3 por aqui.");
    }

    void statusMudou() {
        if (!a.conectado() && ligado()) desligar();
        if (a.abaAtual() == ABA) msgPadrao();
    }

    private void ligar() {
        if (ligado()) return;
        if (!a.conectado()) { if (sw != null) sw.setChecked(false); msgPadrao(); return; }
        remoto = new Remoto(a.ip(), new Remoto.Erro() {
            public void erro(final String m) {
                a.ui(new Runnable() {
                    public void run() {
                        desligar();
                        if (lblMsg != null) { lblMsg.setText(m); lblMsg.setTextColor(Ui.VERMELHO); }
                    }
                });
            }
        });
        a.getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if (pad != null) pad.setLigado(true);
        mandar();
        msgPadrao();
    }

    /** Solta tudo no PS3 e desliga (também ao sair da aba ou do app). */
    void desligar() {
        if (remoto != null) { remoto.parar(); remoto = null; }
        fisBotoes.clear(); fisDpad.clear(); fLx = fLy = fRx = fRy = 0;
        a.getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if (pad != null) pad.setLigado(false);
        if (sw != null && sw.isChecked()) sw.setChecked(false);
        msgPadrao();
    }

    private void mandar() {
        if (remoto == null) return;
        Set<String> bt = new HashSet<String>(telaBotoes), dpad = new HashSet<String>(telaDpad);
        bt.addAll(fisBotoes);
        dpad.addAll(fisDpad);
        float lx = Math.abs(fLx) > Math.abs(tLx) ? fLx : tLx, ly = Math.abs(fLy) > Math.abs(tLy) ? fLy : tLy;
        float rx = Math.abs(fRx) > Math.abs(tRx) ? fRx : tRx, ry = Math.abs(fRy) > Math.abs(tRy) ? fRy : tRy;
        remoto.enviar(Remoto.comando(bt, dpad, lx, ly, rx, ry));
    }

    // ------------------------------------------------------------------ controle físico (Bluetooth/USB no celular)
    private static boolean doControle(int fonte) {
        return (fonte & InputDevice.SOURCE_GAMEPAD) == InputDevice.SOURCE_GAMEPAD
                || (fonte & InputDevice.SOURCE_JOYSTICK) == InputDevice.SOURCE_JOYSTICK
                || (fonte & InputDevice.SOURCE_DPAD) == InputDevice.SOURCE_DPAD;
    }

    private static String botaoDe(int code) {
        switch (code) {
            case KeyEvent.KEYCODE_BUTTON_A: return "cross";
            case KeyEvent.KEYCODE_BUTTON_B: return "circle";
            case KeyEvent.KEYCODE_BUTTON_X: return "square";
            case KeyEvent.KEYCODE_BUTTON_Y: return "triangle";
            case KeyEvent.KEYCODE_BUTTON_L1: return "L1";
            case KeyEvent.KEYCODE_BUTTON_R1: return "R1";
            case KeyEvent.KEYCODE_BUTTON_L2: return "L2";
            case KeyEvent.KEYCODE_BUTTON_R2: return "R2";
            case KeyEvent.KEYCODE_BUTTON_THUMBL: return "L3";
            case KeyEvent.KEYCODE_BUTTON_THUMBR: return "R3";
            case KeyEvent.KEYCODE_BUTTON_SELECT: return "select";
            case KeyEvent.KEYCODE_BUTTON_START: return "start";
            case KeyEvent.KEYCODE_BUTTON_MODE: return "psbtn";
            case KeyEvent.KEYCODE_DPAD_UP: return "up";
            case KeyEvent.KEYCODE_DPAD_DOWN: return "down";
            case KeyEvent.KEYCODE_DPAD_LEFT: return "left";
            case KeyEvent.KEYCODE_DPAD_RIGHT: return "right";
            default: return null;
        }
    }

    /** true = o evento era do controle e foi usado aqui. */
    boolean tecla(KeyEvent e) {
        if (!ligado() || a.abaAtual() != ABA || !doControle(e.getSource())) return false;
        String b = botaoDe(e.getKeyCode());
        if (b == null) return e.getKeyCode() == KeyEvent.KEYCODE_BACK && (e.getSource() & InputDevice.SOURCE_GAMEPAD) != 0;
        boolean dir = b.equals("up") || b.equals("down") || b.equals("left") || b.equals("right");
        Set<String> alvo = dir ? fisDpad : fisBotoes;
        if (e.getAction() == KeyEvent.ACTION_DOWN) alvo.add(b); else if (e.getAction() == KeyEvent.ACTION_UP) alvo.remove(b);
        mandar();
        return true;
    }

    boolean movimento(MotionEvent e) {
        if (!ligado() || a.abaAtual() != ABA || !doControle(e.getSource()) || e.getAction() != MotionEvent.ACTION_MOVE) return false;
        fLx = zona(e.getAxisValue(MotionEvent.AXIS_X));
        fLy = zona(e.getAxisValue(MotionEvent.AXIS_Y));
        fRx = zona(e.getAxisValue(MotionEvent.AXIS_Z));
        fRy = zona(e.getAxisValue(MotionEvent.AXIS_RZ));
        float hx = e.getAxisValue(MotionEvent.AXIS_HAT_X), hy = e.getAxisValue(MotionEvent.AXIS_HAT_Y);
        fisDpad.clear();
        if (hy < -0.5f) fisDpad.add("up"); else if (hy > 0.5f) fisDpad.add("down");
        if (hx < -0.5f) fisDpad.add("left"); else if (hx > 0.5f) fisDpad.add("right");
        float lt = Math.max(e.getAxisValue(MotionEvent.AXIS_LTRIGGER), e.getAxisValue(MotionEvent.AXIS_BRAKE));
        float rt = Math.max(e.getAxisValue(MotionEvent.AXIS_RTRIGGER), e.getAxisValue(MotionEvent.AXIS_GAS));
        if (lt > 0.4f) fisBotoes.add("L2"); else if (lt < 0.2f && lt >= 0) gatilhoSolto("L2", e);
        if (rt > 0.4f) fisBotoes.add("R2"); else if (rt < 0.2f && rt >= 0) gatilhoSolto("R2", e);
        mandar();
        return true;
    }

    /** Só solta L2/R2 pelo eixo se o controle tiver esse eixo (senão quem manda é o botão). */
    private void gatilhoSolto(String b, MotionEvent e) {
        InputDevice d = e.getDevice();
        if (d == null) return;
        int[] eixos = b.equals("L2") ? new int[]{MotionEvent.AXIS_LTRIGGER, MotionEvent.AXIS_BRAKE}
                : new int[]{MotionEvent.AXIS_RTRIGGER, MotionEvent.AXIS_GAS};
        for (int x : eixos) if (d.getMotionRange(x, e.getSource()) != null) { fisBotoes.remove(b); return; }
    }

    private static float zona(float v) { return Math.abs(v) < 0.15f ? 0 : v; }
}
