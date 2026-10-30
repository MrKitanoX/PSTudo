# Componentes de terceiros

## ps3iso-utils / makeps3iso

- Autor original: Estwald. Builds e manutenção: bucanero (https://github.com/bucanero/ps3iso-utils)
- Licença: GNU General Public License v3.0 (texto completo em `third_party/ps3iso-utils/LICENSE`)
- Incluído em: `third_party/ps3iso-utils/src` (código-fonte, sem modificações) e
  `third_party/ps3iso-utils/bin/makeps3iso.exe` (compilado a partir desse código com MinGW-w64:
  `x86_64-w64-mingw32-gcc -O2 -s -D__MSVCRT__ makeps3iso.c -o makeps3iso.exe`).
- Versão do código: ver `third_party/ps3iso-utils/VERSAO.txt`.

## AMD FidelityFX Super Resolution 1.0 (EASU e RCAS)

Os shaders de ampliação e nitidez da tela cheia (`FS_ESCALA` e `FS_RCAS` em `pstudo.py`) são adaptações do EASU e do RCAS do FSR 1.

```
Copyright (c) 2021 Advanced Micro Devices, Inc. All rights reserved.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

## RIFE 4.6 (Real-Time Intermediate Flow Estimation)

A fluidez com IA da aba Tela usa a arquitetura e os pesos do RIFE 4.6. Os pesos (`assets/rife46.bin`) foram
convertidos do modelo `rife-v4.6` do rife-ncnn-vulkan com `tools/empacotar_rife.py`; a rede roda em shaders
OpenGL escritos para o PSTudo (`pstudo_ia.py`).

- Practical-RIFE: https://github.com/hzwer/Practical-RIFE

```
MIT License

Copyright (c) 2021 hzwer

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- rife-ncnn-vulkan: https://github.com/nihui/rife-ncnn-vulkan

```
The MIT License (MIT)

Copyright (c) 2020 nihui

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Não incluídos (baixados ou usados no console)

- **XPAD Revolution** (GabaRSk): baixado do GitHub oficial quando o usuário clica em "Instalar".
- **webMAN MOD** (aldostools): instalado pelo usuário no PS3.

## Bibliotecas Python usadas no .exe

| Biblioteca | Licença |
|---|---|
| customtkinter | MIT |
| Pillow | MIT-CMU (HPND) |
| opencv-python-headless | Apache 2.0 (o pacote inclui o FFmpeg, LGPL) |
| NumPy | BSD-3-Clause |
| sounddevice (inclui PortAudio) | MIT |
| pygrabber | MIT |
| comtypes | MIT |
| pygame-ce (inclui SDL2) | LGPL 2.1 |
| ModernGL / glcontext | MIT |
| PyCryptodome | BSD-2-Clause / Domínio público |
| PyInstaller (ferramenta de build) | GPL 2.0 com exceção para programas gerados |
