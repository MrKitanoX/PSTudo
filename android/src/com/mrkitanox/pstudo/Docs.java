package com.mrkitanox.pstudo;

import android.content.ContentResolver;
import android.database.Cursor;
import android.net.Uri;
import android.provider.DocumentsContract;
import android.provider.OpenableColumns;

import java.io.FileNotFoundException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.List;

/** Arquivos e pastas do celular escolhidos pelo seletor do Android (Storage Access Framework). */
public final class Docs {
    private Docs() { }

    public static class No {
        public final String id, nome;
        public final boolean pasta;
        public final long tamanho;
        public No(String id, String nome, boolean pasta, long tamanho) { this.id = id; this.nome = nome; this.pasta = pasta; this.tamanho = tamanho; }
    }

    /** Um arquivo daquela pasta, para enviar: caminho relativo ("PS3_GAME/USRDIR/EBOOT.BIN"). */
    public static class Arquivo {
        public final String id, relativo;
        public final long tamanho;
        public Arquivo(String id, String relativo, long tamanho) { this.id = id; this.relativo = relativo; this.tamanho = tamanho; }
    }

    public static String raiz(Uri arvore) { return DocumentsContract.getTreeDocumentId(arvore); }

    public static List<No> filhos(ContentResolver cr, Uri arvore, String id) {
        List<No> l = new ArrayList<No>();
        Uri u = DocumentsContract.buildChildDocumentsUriUsingTree(arvore, id);
        Cursor c = null;
        try {
            c = cr.query(u, new String[]{DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                    DocumentsContract.Document.COLUMN_DISPLAY_NAME, DocumentsContract.Document.COLUMN_MIME_TYPE,
                    DocumentsContract.Document.COLUMN_SIZE}, null, null, null);
            while (c != null && c.moveToNext()) {
                boolean pasta = DocumentsContract.Document.MIME_TYPE_DIR.equals(c.getString(2));
                l.add(new No(c.getString(0), c.getString(1), pasta, c.isNull(3) ? 0 : c.getLong(3)));
            }
        } catch (RuntimeException ignored) {
        } finally {
            if (c != null) c.close();
        }
        return l;
    }

    public static String nomePasta(ContentResolver cr, Uri arvore) {
        Uri u = DocumentsContract.buildDocumentUriUsingTree(arvore, raiz(arvore));
        String n = nome(cr, u);
        if (n != null) return n;
        String id = raiz(arvore);
        int i = Math.max(id.lastIndexOf('/'), id.lastIndexOf(':'));
        return id.substring(i + 1);
    }

    /** Todos os arquivos dentro da pasta (com subpastas). */
    public static List<Arquivo> todos(ContentResolver cr, Uri arvore) {
        List<Arquivo> l = new ArrayList<Arquivo>();
        juntar(cr, arvore, raiz(arvore), "", l);
        return l;
    }

    private static void juntar(ContentResolver cr, Uri arvore, String id, String rel, List<Arquivo> l) {
        for (No n : filhos(cr, arvore, id)) {
            String r = rel.isEmpty() ? n.nome : rel + "/" + n.nome;
            if (n.pasta) juntar(cr, arvore, n.id, r, l);
            else l.add(new Arquivo(n.id, r, n.tamanho));
        }
    }

    public static No filho(ContentResolver cr, Uri arvore, String id, String nome) {
        for (No n : filhos(cr, arvore, id)) if (n.nome.equalsIgnoreCase(nome)) return n;
        return null;
    }

    public static InputStream abrir(ContentResolver cr, Uri arvore, String id) throws FileNotFoundException {
        return cr.openInputStream(DocumentsContract.buildDocumentUriUsingTree(arvore, id));
    }

    /** Nome do jogo de uma pasta: TITLE do PARAM.SFO (PS3_GAME/PARAM.SFO ou PARAM.SFO). */
    public static String tituloJogo(ContentResolver cr, Uri arvore) {
        try {
            String r = raiz(arvore);
            No ps3 = filho(cr, arvore, r, "PS3_GAME");
            No sfo = ps3 != null ? filho(cr, arvore, ps3.id, "PARAM.SFO") : filho(cr, arvore, r, "PARAM.SFO");
            if (sfo != null) return Sfo.titulo(abrir(cr, arvore, sfo.id));
        } catch (Exception ignored) { }
        return null;
    }

    public static String nome(ContentResolver cr, Uri u) {
        Cursor c = null;
        try {
            c = cr.query(u, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null);
            if (c != null && c.moveToFirst()) return c.getString(0);
        } catch (RuntimeException ignored) {
        } finally {
            if (c != null) c.close();
        }
        String s = u.getLastPathSegment();
        return s == null ? "arquivo" : s.substring(s.lastIndexOf('/') + 1);
    }

    public static long tamanho(ContentResolver cr, Uri u) {
        Cursor c = null;
        try {
            c = cr.query(u, new String[]{OpenableColumns.SIZE}, null, null, null);
            if (c != null && c.moveToFirst() && !c.isNull(0)) return c.getLong(0);
        } catch (RuntimeException ignored) {
        } finally {
            if (c != null) c.close();
        }
        return 0;
    }

    /** Cria um arquivo (ou pasta, com mime = MIME_TYPE_DIR) dentro de uma pasta escolhida. Devolve o id. */
    public static String criar(ContentResolver cr, Uri arvore, String paiId, String mime, String nome) throws FileNotFoundException {
        Uri pai = DocumentsContract.buildDocumentUriUsingTree(arvore, paiId);
        Uri novo = DocumentsContract.createDocument(cr, pai, mime, nome);
        if (novo == null) throw new FileNotFoundException("Não consegui criar " + nome);
        return DocumentsContract.getDocumentId(novo);
    }

    public static OutputStream gravar(ContentResolver cr, Uri arvore, String id) throws FileNotFoundException {
        return cr.openOutputStream(DocumentsContract.buildDocumentUriUsingTree(arvore, id));
    }
}
