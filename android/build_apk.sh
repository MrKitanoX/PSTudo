#!/usr/bin/env bash
# Gera o PSTudo.apk sem Gradle nem Android Studio.
# Precisa (Ubuntu/Debian):
#   sudo apt install openjdk-17-jdk android-sdk-build-tools android-sdk-platform-23 dalvik-exchange apksigner zipalign
# Uso: ./build_apk.sh            -> android/dist/PSTudo.apk
# A chave de assinatura fica em android/pstudo.keystore (criada na primeira vez; guarde-a para poder
# atualizar o app no celular sem desinstalar). Senha: variável KS_SENHA (padrão "pstudo").
set -euo pipefail
cd "$(dirname "$0")"

SDK=${ANDROID_SDK:-/usr/lib/android-sdk}
JAR=${ANDROID_JAR:-$(ls "$SDK"/platforms/android-*/android.jar | sort -V | tail -1)}
BT=$(for d in $(ls -d "$SDK"/build-tools/*/ | sort -V); do [ -e "$d/dx" ] && echo "$d"; done | tail -1)
AAPT=${AAPT:-$(command -v aapt || echo "$BT/aapt")}
DX="$BT/dx"
SENHA=${KS_SENHA:-pstudo}

rm -rf build && mkdir -p build/gen build/obj dist
echo "== recursos"
mkdir -p build/assets/idiomas && cp ../assets/idiomas/*.json build/assets/idiomas/      # mesmas traduções do PC
"$AAPT" package -f -m -J build/gen -M AndroidManifest.xml -S res -A build/assets -I "$JAR" -F build/base.apk
echo "== java"
javac -nowarn -encoding UTF-8 -source 8 -target 8 -bootclasspath "$JAR" -d build/obj \
      $(find src build/gen -name '*.java') 2>&1 | grep -v '^warning:' || true
[ -n "$(find build/obj -name MainActivity.class)" ] || { echo "falhou ao compilar"; exit 1; }
echo "== dex"
"$DX" --dex --min-sdk-version=23 --output=build/classes.dex build/obj
(cd build && "$AAPT" add base.apk classes.dex >/dev/null)
echo "== assinar"
zipalign -f 4 build/base.apk build/alinhado.apk
if [ ! -f pstudo.keystore ]; then
  keytool -genkeypair -keystore pstudo.keystore -storepass "$SENHA" -keypass "$SENHA" -alias pstudo \
          -keyalg RSA -keysize 2048 -validity 20000 -dname "CN=MrKitanoX, O=PSTudo"
fi
apksigner sign --ks pstudo.keystore --ks-pass "pass:$SENHA" --key-pass "pass:$SENHA" --out dist/PSTudo.apk build/alinhado.apk
apksigner verify dist/PSTudo.apk
echo "Pronto: android/dist/PSTudo.apk"
