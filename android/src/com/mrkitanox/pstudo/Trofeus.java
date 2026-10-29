package com.mrkitanox.pstudo;

import android.util.Xml;

import org.xmlpull.v1.XmlPullParser;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/** Troféus do PS3: ler, destravar localmente e reassinar o PARAM.PFD (mesma lógica da versão de PC).
    Só TROPUSR.DAT e TROPTRNS.DAT mudam, e as chaves deles são iguais em todo PS3. Antes de gravar,
    a assinatura atual é recalculada e precisa bater com a do PS3; se não bater, nada é alterado. */
public final class Trofeus {
    private Trofeus() { }

    public static class Erro extends IOException { Erro(String m) { super(m); } }

    static final byte[] SYSCON = hex("D413B89663E1FE9F75143D3BB4565274");
    static final byte[] KEYGEN = hex("6B1ACEA246B745FD8F93763B920594CD53483B82");
    static final Map<String, byte[]> CHAVES = new HashMap<String, byte[]>();
    static {
        CHAVES.put("PARAM.SFO", hex("5D5B647917024E9BB8D330486B996E795D7F4392"));
        CHAVES.put("TROPSYS.DAT", hex("B080C40FF358643689281736A6BF15892CFEA436"));
        CHAVES.put("TROPUSR.DAT", hex("8711EFF406913F0937F115FAB23DE1A9897A789A"));
        CHAVES.put("TROPTRNS.DAT", hex("91EE81555ACC1C4FB5AAE5462CFE1C62A4AF36A5"));
        CHAVES.put("TROPCONF.SFM", hex("E2ED33C71C444EEBC1E23D635AD8E82F4ECA4E94"));
    }
    static final long MAGIC = 0x818F54AD00010000L;
    static final int SYNC = 0x00010000, NAO_SYNC = 0x00001000;
    public static final String[] TIPOS = {"", "Platina", "Ouro", "Prata", "Bronze"};

    static byte[] hex(String s) {
        byte[] b = new byte[s.length() / 2];
        for (int i = 0; i < b.length; i++) b[i] = (byte) Integer.parseInt(s.substring(2 * i, 2 * i + 2), 16);
        return b;
    }

    // ---------------------------------------------------------------- utilidades big-endian
    static int u32(byte[] d, int o) { return ByteBuffer.wrap(d, o, 4).getInt(); }
    static long u64(byte[] d, int o) { return ByteBuffer.wrap(d, o, 8).getLong(); }
    static void p32(byte[] d, int o, int v) { ByteBuffer.wrap(d, o, 4).putInt(v); }
    static void p64(byte[] d, int o, long v) { ByteBuffer.wrap(d, o, 8).putLong(v); }

    static byte[] hmac(byte[] chave, byte[]... partes) {
        try {
            Mac m = Mac.getInstance("HmacSHA1");
            m.init(new SecretKeySpec(chave, "HmacSHA1"));
            for (byte[] p : partes) m.update(p);
            return m.doFinal();
        } catch (Exception e) { throw new RuntimeException(e); }
    }

    static byte[] aes(String modo, int op, byte[] chave, byte[] iv, byte[] dados) {
        try {
            Cipher c = Cipher.getInstance("AES/" + modo + "/NoPadding");
            SecretKeySpec k = new SecretKeySpec(chave, "AES");
            if (iv != null) c.init(op, k, new IvParameterSpec(iv)); else c.init(op, k);
            return c.doFinal(dados);
        } catch (Exception e) { throw new RuntimeException(e); }
    }

    public static long tempoPs3(long ms) { return ms * 1000L + 62135596800000000L; }
    public static long tempoMs(long t) { return t == 0 ? 0 : (t - 62135596800000000L) / 1000L; }

    // ---------------------------------------------------------------- PARAM.PFD
    static class Pfd {
        static final int ENTRADA = 272;
        final byte[] d;
        final long versao;
        final byte[] iv, sig, chaveReal;
        final int capacidade, reservadas, usadas, iniEntradas, iniAss;

        Pfd(byte[] dados) throws Erro {
            d = dados.clone();
            if (d.length < 128 || u64(d, 0) != 0x50464442L) throw new Erro("PARAM.PFD inválido");
            versao = u64(d, 8);
            if (versao != 3 && versao != 4) throw new Erro("PARAM.PFD de versão desconhecida");
            iv = Arrays.copyOfRange(d, 16, 32);
            sig = aes("CBC", Cipher.DECRYPT_MODE, SYSCON, iv, Arrays.copyOfRange(d, 32, 96));
            byte[] chave = Arrays.copyOfRange(sig, 40, 60);
            chaveReal = versao == 4 ? hmac(KEYGEN, chave) : chave;
            long cap = u64(d, 96), res = u64(d, 104), us = u64(d, 112);
            if (cap <= 0 || cap >= 1000 || us > res || res >= 1000) throw new Erro("PARAM.PFD com tabela estranha");
            capacidade = (int) cap; reservadas = (int) res; usadas = (int) us;
            iniEntradas = 96 + 24 + capacidade * 8;
            iniAss = iniEntradas + reservadas * ENTRADA;
            if (iniAss + capacidade * 20 > d.length) throw new Erro("PARAM.PFD cortado");
        }

        long indice(int i) { return u64(d, 120 + i * 8); }
        int ofs(int n) { return iniEntradas + n * ENTRADA; }

        String nome(int n) {
            int o = ofs(n) + 8, z = o;
            while (z < o + 65 && d[z] != 0) z++;
            return new String(d, o, z - o, Ftp.LATIN1).toUpperCase(java.util.Locale.ROOT);
        }

        Map<String, Integer> arquivos() {
            Map<String, Integer> r = new LinkedHashMap<String, Integer>();
            for (int n = 0; n < usadas; n++) r.put(nome(n), n);
            return r;
        }

        long tamanho(String nome) { return u64(d, ofs(arquivos().get(nome)) + 264); }

        byte[] hashBalde(int i) {
            long atual = indice(i);
            try {
                Mac m = Mac.getInstance("HmacSHA1");
                m.init(new SecretKeySpec(chaveReal, "HmacSHA1"));
                int vistos = 0;
                while (atual < reservadas && vistos <= reservadas) {
                    int o = ofs((int) atual);
                    m.update(d, o + 8, 65);
                    m.update(d, o + 80, 192);
                    atual = u64(d, o);
                    vistos++;
                }
                return m.doFinal();
            } catch (Exception e) { throw new RuntimeException(e); }
        }

        static byte[] hashArquivo(String nome, byte[] conteudo) {
            byte[] k = CHAVES.get(nome);
            return k == null ? null : hmac(k, conteudo);
        }

        byte[] top() { return hmac(chaveReal, Arrays.copyOfRange(d, 96, 96 + 24 + capacidade * 8)); }
        byte[] base() { return hmac(chaveReal, Arrays.copyOfRange(d, iniAss, iniAss + capacidade * 20)); }

        List<String> conferir(Map<String, byte[]> arqs) {
            List<String> erros = new ArrayList<String>();
            if (!Arrays.equals(top(), Arrays.copyOfRange(sig, 20, 40))) erros.add("topo");
            if (!Arrays.equals(base(), Arrays.copyOfRange(sig, 0, 20))) erros.add("base");
            for (int i = 0; i < capacidade; i++)
                if (!Arrays.equals(hashBalde(i), Arrays.copyOfRange(d, iniAss + i * 20, iniAss + i * 20 + 20))) erros.add("entrada " + i);
            for (Map.Entry<String, Integer> e : arquivos().entrySet()) {
                byte[] c = arqs.get(e.getKey());
                if (c == null) continue;
                byte[] h = hashArquivo(e.getKey(), c);
                int o = ofs(e.getValue()) + 144;
                if (h != null && !Arrays.equals(h, Arrays.copyOfRange(d, o, o + 20))) erros.add(e.getKey());
            }
            return erros;
        }

        byte[] atualizar(Map<String, byte[]> novos) throws Erro {
            Map<String, Integer> nomes = arquivos();
            for (Map.Entry<String, byte[]> e : novos.entrySet()) {
                Integer n = nomes.get(e.getKey());
                if (n == null) throw new Erro(e.getKey() + " não está no PARAM.PFD");
                System.arraycopy(hashArquivo(e.getKey(), e.getValue()), 0, d, ofs(n) + 144, 20);
            }
            for (int i = 0; i < capacidade; i++) System.arraycopy(hashBalde(i), 0, d, iniAss + i * 20, 20);
            System.arraycopy(base(), 0, sig, 0, 20);
            System.arraycopy(top(), 0, sig, 20, 20);
            System.arraycopy(aes("CBC", Cipher.ENCRYPT_MODE, SYSCON, iv, sig), 0, d, 32, 64);
            return d.clone();
        }

        byte[] chaveDados(String nome) {
            int o = ofs(arquivos().get(nome)) + 80;
            byte[] k = CHAVES.get(nome);
            byte[] dec = aes("CBC", Cipher.DECRYPT_MODE, SYSCON, Arrays.copyOf(k, 16), Arrays.copyOfRange(d, o, o + 64));
            return Arrays.copyOf(dec, 16);
        }

        byte[] contador(byte[] k, int blocos) {
            ByteBuffer b = ByteBuffer.allocate(blocos * 16);
            for (int i = 0; i < blocos; i++) { b.putLong(i); b.putLong(0); }
            return aes("ECB", Cipher.ENCRYPT_MODE, k, null, b.array());
        }

        byte[] decifrar(String nome, byte[] dados) {
            int tam = (int) tamanho(nome), alinhado = (tam + 15) / 16 * 16;
            byte[] k = chaveDados(nome);
            byte[] dec = aes("ECB", Cipher.DECRYPT_MODE, k, null, Arrays.copyOf(dados, alinhado));
            byte[] ctr = contador(k, alinhado / 16);
            for (int i = 0; i < dec.length; i++) dec[i] ^= ctr[i];
            return Arrays.copyOf(dec, tam);
        }

        byte[] cifrar(String nome, byte[] dados) {
            int alinhado = (dados.length + 15) / 16 * 16;
            byte[] k = chaveDados(nome);
            byte[] m = Arrays.copyOf(dados, alinhado);
            byte[] ctr = contador(k, alinhado / 16);
            for (int i = 0; i < m.length; i++) m[i] ^= ctr[i];
            return aes("ECB", Cipher.ENCRYPT_MODE, k, null, m);
        }
    }

    // ---------------------------------------------------------------- TROPUSR.DAT / TROPTRNS.DAT
    static Map<Integer, long[]> registros(byte[] d, String nome) throws Erro {
        if (d.length < 48 || u64(d, 0) != MAGIC) throw new Erro(nome + " inválido");
        int n = u32(d, 8);
        if (n <= 0 || n >= 64 || 48 + n * 32 > d.length) throw new Erro(nome + " com tabela estranha");
        Map<Integer, long[]> r = new HashMap<Integer, long[]>();
        for (int i = 0; i < n; i++) {
            int o = 48 + i * 32;
            r.put(u32(d, o), new long[]{u64(d, o + 16), u32(d, o + 4), u32(d, o + 12)});
        }
        return r;
    }

    static int[] blocos(byte[] d, long ofs, int qtd) throws Erro {
        int[] r = new int[qtd];
        long o = ofs;
        for (int k = 0; k < qtd; k++) {
            if (o + 16 > d.length) throw new Erro("bloco fora do arquivo");
            int tam = u32(d, (int) o + 4);
            if (tam <= 0 || o + 16 + tam > d.length) throw new Erro("bloco com tamanho estranho");
            r[k] = (int) o + 16;
            o += 16 + tam;
        }
        return r;
    }

    public static class Trofeu {
        public int id, tipo;
        public boolean destravado, sync, oculto;
        public long tempo;
        public String nome = "", detalhe = "", grupo = "";
    }

    static class Usr {
        final byte[] d;
        final String npcomm;
        final int total, lista, r7;
        final int[] tipos, tempos;

        Usr(byte[] dados) throws Erro {
            d = dados.clone();
            Map<Integer, long[]> regs = registros(d, "TROPUSR.DAT");
            for (int k = 3; k <= 7; k++) if (!regs.containsKey(k)) throw new Erro("TROPUSR.DAT incompleto");
            int b3 = (int) regs.get(3)[0] + 16;
            npcomm = texto(d, b3, 16);
            total = u32(d, b3 + 24);
            if (total <= 0 || total > 128) throw new Erro("número de troféus estranho");
            tipos = blocos(d, regs.get(4)[0], total);
            lista = (int) regs.get(5)[0] + 16;
            tempos = blocos(d, regs.get(6)[0], total);
            r7 = (int) regs.get(7)[0] + 16;
        }

        int tipo(int i) { return u32(d, tipos[i] + 4); }

        Trofeu info(int i) {
            Trofeu t = new Trofeu();
            int o = tempos[i];
            t.id = i; t.tipo = tipo(i);
            t.destravado = u32(d, o + 4) != 0;
            t.sync = (u32(d, o + 8) & SYNC) != 0;
            t.tempo = u64(d, o + 16);
            return t;
        }

        long maiorTempo() {
            long m = 0;
            for (int o : tempos) m = Math.max(m, u64(d, o + 16));
            for (int k : new int[]{16, 32, 64}) m = Math.max(m, u64(d, lista + k));
            return m;
        }

        boolean destravar(int i, long t) {
            int o = tempos[i];
            if (u32(d, o + 4) != 0) return false;
            p32(d, o + 4, 1); p32(d, o + 8, NAO_SYNC); p64(d, o + 16, t); p64(d, o + 24, t);
            p32(d, lista + 112, u32(d, lista + 112) + 1);
            p32(d, r7, u32(d, r7) + 1);
            int oa = lista + 128 + (i / 32) * 4;
            p32(d, oa, u32(d, oa) | (1 << (i % 32)));
            if (u64(d, lista + 64) < t) { p64(d, lista + 64, t); p64(d, lista + 72, t); }
            p64(d, lista + 32, t); p64(d, lista + 40, t);
            return true;
        }
    }

    static class Trns {
        final byte[] d;
        final String npcomm;
        final int b3, ini, passo, capacidade, tipoBloco;
        int contagem;

        Trns(byte[] dados) throws Erro {
            d = dados.clone();
            Map<Integer, long[]> regs = registros(d, "TROPTRNS.DAT");
            if (!regs.containsKey(3) || !regs.containsKey(4)) throw new Erro("TROPTRNS.DAT incompleto");
            b3 = (int) regs.get(3)[0] + 16;
            npcomm = texto(d, b3, 16);
            ini = (int) regs.get(4)[0];
            int tb = u32(d, ini + 4);
            if (tb < 64) throw new Erro("TROPTRNS.DAT com bloco estranho");
            passo = 16 + tb;
            long fim = d.length;
            for (long[] r : regs.values()) if (r[0] > ini && r[0] < fim) fim = r[0];   // não invade a parte seguinte
            capacidade = (int) ((fim - ini) / passo) - 1;
            tipoBloco = u32(d, ini);
            contagem = u32(d, b3 + 20);
            if (contagem < 1 || contagem > capacidade + 1) throw new Erro("contagem estranha no TROPTRNS.DAT");
        }

        List<long[]> ganhos() {     // {id, tempo}
            List<long[]> r = new ArrayList<long[]>();
            for (int k = 1; k < contagem; k++) {
                int o = ini + k * passo + 16;
                r.add(new long[]{u32(d, o + 32), u64(d, o + 48)});
            }
            return r;
        }

        long maiorTempo() {
            long m = 0;
            for (long[] g : ganhos()) m = Math.max(m, g[1]);
            return m;
        }

        /** Confere o formato (ganhos + 1 na contagem, próximo espaço vazio). Se não bater, é melhor não mexer. */
        void conferirFormato(int total) throws Erro {
            for (int k = 1; k < contagem; k++) {
                int cab = ini + k * passo, o = cab + 16;
                if (u32(d, cab) != tipoBloco || u32(d, cab + 4) != passo - 16 || u32(d, o + 4) == 0
                        || (u32(d, o + 32) & 0xFFFFFFFFL) >= total)
                    throw new Erro("o TROPTRNS.DAT está num formato que o PSTudo não reconhece. Nada foi alterado.");
            }
            conferirVazio(contagem);
        }

        void conferirVazio(int k) throws Erro {
            if (k > capacidade) throw new Erro("não há espaço no TROPTRNS.DAT");
            int cab = ini + k * passo, o = cab + 16;
            if (u32(d, cab) != tipoBloco || u32(d, cab + 4) != passo - 16 || u32(d, o + 4) != 0 || u32(d, o + 8) != 0
                    || u32(d, o + 32) != 0 || u64(d, o + 48) != 0 || u64(d, o + 56) != 0)
                throw new Erro("o espaço livre do TROPTRNS.DAT não está vazio. Nada foi alterado.");
        }

        boolean destravar(int i, int tipo, long t) throws Erro {
            for (long[] g : ganhos()) if (g[0] == i) throw new Erro("TROPUSR.DAT e TROPTRNS.DAT não concordam sobre este troféu. Nada foi alterado.");
            int k = contagem;
            conferirVazio(k);
            int o = ini + k * passo + 16;
            p32(d, o, k); p32(d, o + 4, 2); p32(d, o + 8, 0); p32(d, o + 12, 0);
            Arrays.fill(d, o + 16, o + passo - 16, (byte) 0);
            p32(d, o + 32, i); p32(d, o + 36, tipo); p32(d, o + 40, 0x1000); p32(d, o + 44, 0);
            p64(d, o + 48, t); p64(d, o + 56, t);
            contagem++;
            p32(d, b3 + 20, contagem);
            return true;
        }
    }

    static String texto(byte[] d, int o, int max) {
        int z = o;
        while (z < o + max && z < d.length && d[z] != 0) z++;
        return new String(d, o, z - o, Ftp.LATIN1);
    }

    // ---------------------------------------------------------------- nomes (TROP.SFM)
    /** Lê os nomes dos troféus; devolve o nome do jogo. */
    static String lerSfm(byte[] dados, Map<Integer, Trofeu> destino) {
        String jogo = "";
        int i = indexOf(dados, "<?xml".getBytes());
        if (i < 0) i = indexOf(dados, "<trophyconf".getBytes());
        if (i < 0) return jogo;
        int z = i;
        while (z < dados.length && dados[z] != 0) z++;
        try {
            XmlPullParser p = Xml.newPullParser();
            p.setInput(new ByteArrayInputStream(dados, i, z - i), "UTF-8");
            Trofeu atual = null;
            String campo = null;
            for (int ev = p.getEventType(); ev != XmlPullParser.END_DOCUMENT; ev = p.next()) {
                if (ev == XmlPullParser.START_TAG) {
                    String n = p.getName();
                    if ("trophy".equals(n)) {
                        try {
                            atual = new Trofeu();
                            atual.id = Integer.parseInt(p.getAttributeValue(null, "id"));
                            atual.oculto = "yes".equals(p.getAttributeValue(null, "hidden"));
                            String gid = p.getAttributeValue(null, "gid");
                            atual.grupo = gid == null ? "" : gid.trim();
                            destino.put(atual.id, atual);
                        } catch (Exception e) { atual = null; }
                    }
                    campo = n;
                } else if (ev == XmlPullParser.TEXT && campo != null) {
                    String t = p.getText() == null ? "" : p.getText().trim();
                    if (t.isEmpty()) continue;
                    if ("title-name".equals(campo) && jogo.isEmpty()) jogo = t;
                    else if (atual != null && "name".equals(campo)) atual.nome = t;
                    else if (atual != null && "detail".equals(campo)) atual.detalhe = t;
                } else if (ev == XmlPullParser.END_TAG) {
                    if ("trophy".equals(p.getName())) atual = null;
                    campo = null;
                }
            }
        } catch (Exception ignored) { }
        return jogo;
    }

    static int indexOf(byte[] d, byte[] alvo) {
        outer:
        for (int i = 0; i + alvo.length <= d.length; i++) {
            for (int j = 0; j < alvo.length; j++) if (d[i + j] != alvo[j]) continue outer;
            return i;
        }
        return -1;
    }

    /** Lista dos troféus (com nomes, se houver um .SFM). */
    public static List<Trofeu> resumo(byte[] tropusr, byte[] sfm) throws Erro {
        Usr u = new Usr(tropusr);
        Map<Integer, Trofeu> nomes = new HashMap<Integer, Trofeu>();
        if (sfm != null) lerSfm(sfm, nomes);
        List<Trofeu> r = new ArrayList<Trofeu>();
        for (int i = 0; i < u.total; i++) {
            Trofeu t = u.info(i);
            Trofeu n = nomes.get(i);
            if (n != null) { t.nome = n.nome; t.detalhe = n.detalhe; t.oculto = n.oculto; }
            if (t.nome.isEmpty()) t.nome = "Troféu " + i;
            r.add(t);
        }
        return r;
    }

    public static int ganhos(byte[] tropusr) throws Erro {
        Usr u = new Usr(tropusr);
        int n = 0;
        for (int i = 0; i < u.total; i++) if (u.info(i).destravado) n++;
        return n;
    }

    public static int total(byte[] tropusr) throws Erro { return new Usr(tropusr).total; }

    public static class Resultado {
        public final Map<String, byte[]> novos = new LinkedHashMap<String, byte[]>();   // só o que muda
        public int feitos = 0;
        public boolean pulouPlatina = false;
    }

    /** Destrava 'ids'. arqs = arquivos da pasta como estão no PS3. */
    public static Resultado destravar(Map<String, byte[]> arqs, List<Integer> ids, long agoraMs) throws Erro {
        Pfd pfd = new Pfd(arqs.get("PARAM.PFD"));
        List<String> erros = pfd.conferir(arqs);
        if (!erros.isEmpty()) throw new Erro("a assinatura atual destes troféus não bateu com o cálculo do PSTudo ("
                + erros.get(0) + "). Por segurança, nada foi alterado.");
        Usr usr = new Usr(arqs.get("TROPUSR.DAT"));
        Trns trns = new Trns(pfd.decifrar("TROPTRNS.DAT", arqs.get("TROPTRNS.DAT")));
        if (!usr.npcomm.isEmpty() && !trns.npcomm.isEmpty() && !usr.npcomm.equals(trns.npcomm))
            throw new Erro("TROPUSR.DAT e TROPTRNS.DAT são de jogos diferentes.");
        trns.conferirFormato(usr.total);
        java.util.Set<Long> ganhosT = new java.util.HashSet<Long>(), ganhosU = new java.util.HashSet<Long>();
        for (long[] g : trns.ganhos()) ganhosT.add(g[0]);
        for (int i = 0; i < usr.total; i++) if (usr.info(i).destravado) ganhosU.add((long) i);
        if (!ganhosT.equals(ganhosU)) throw new Erro("TROPUSR.DAT e TROPTRNS.DAT não concordam sobre os troféus ganhos. Nada foi alterado.");
        long t = tempoPs3(agoraMs), ultimo = Math.max(trns.maiorTempo(), usr.maiorTempo());
        if (t <= ultimo) t = ultimo + 1000000L;
        // platina (tipo 1) só por último, e só se todos os troféus do jogo base ficarem ganhos
        Map<Integer, Trofeu> conf = new HashMap<Integer, Trofeu>();
        if (arqs.containsKey("TROPCONF.SFM")) lerSfm(arqs.get("TROPCONF.SFM"), conf);
        List<Integer> outros = new ArrayList<Integer>(), platinas = new ArrayList<Integer>();
        for (int i : new TreeSet<Integer>(ids)) {
            if (i < 0 || i >= usr.total || usr.info(i).destravado) continue;
            if (usr.tipo(i) == 1) platinas.add(i); else outros.add(i);
        }
        java.util.Set<Integer> vaoFicar = new java.util.HashSet<Integer>(outros);
        for (int i = 0; i < usr.total; i++) if (usr.info(i).destravado) vaoFicar.add(i);
        boolean baseCompleta = true;
        for (int i = 0; i < usr.total; i++) {
            if (usr.tipo(i) == 1) continue;
            Trofeu c = conf.get(i);
            String g = c == null ? "" : c.grupo;
            if ((g.isEmpty() || g.equals("0") || g.equals("000")) && !vaoFicar.contains(i)) baseCompleta = false;
        }
        Resultado res = new Resultado();
        res.pulouPlatina = !platinas.isEmpty() && !baseCompleta;
        List<Integer> ordem = new ArrayList<Integer>(outros);
        if (!res.pulouPlatina) ordem.addAll(platinas);
        for (int i : ordem) {
            usr.destravar(i, t);
            trns.destravar(i, usr.tipo(i), t);
            t += 1000000L;           // um segundo entre cada um, na ordem
            res.feitos++;
        }
        if (res.feitos == 0) {
            if (res.pulouPlatina) throw new Erro("a platina só pode ser destravada junto com (ou depois de) todos os troféus do jogo.");
            return res;
        }
        Map<String, byte[]> novos = res.novos;
        byte[] cif = pfd.cifrar("TROPTRNS.DAT", trns.d);
        byte[] original = arqs.get("TROPTRNS.DAT");
        if (cif.length < original.length) {     // mantém o tamanho do arquivo
            byte[] x = Arrays.copyOf(cif, original.length);
            System.arraycopy(original, cif.length, x, cif.length, original.length - cif.length);
            cif = x;
        }
        novos.put("TROPUSR.DAT", usr.d.clone());
        novos.put("TROPTRNS.DAT", cif);
        byte[] novoPfd = pfd.atualizar(novos);
        // confere o resultado antes de devolver
        Map<String, byte[]> fim = new HashMap<String, byte[]>(arqs);
        fim.putAll(novos);
        fim.put("PARAM.PFD", novoPfd);
        Pfd p2 = new Pfd(novoPfd);
        if (!p2.conferir(fim).isEmpty()) throw new Erro("a assinatura nova não conferiu. Nada foi alterado.");
        if (new Trns(p2.decifrar("TROPTRNS.DAT", cif)).contagem != trns.contagem)
            throw new Erro("o TROPTRNS.DAT novo não conferiu. Nada foi alterado.");
        novos.put("PARAM.PFD", novoPfd);
        return res;
    }

    static boolean iguais(byte[] a, byte[] b) {
        try { return MessageDigest.isEqual(a, b); } catch (Exception e) { return false; }
    }
}
