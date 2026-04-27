FROM emscripten/emsdk:3.1.73

# Install Rust toolchain inside the Emscripten container.
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain stable --target wasm32-unknown-emscripten
ENV PATH="/root/.cargo/bin:${PATH}"

# Build-time deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake pkg-config python3 ca-certificates git \
    clang libclang-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# ── zlib (required by libpng and leptonica PNG support) ───────────────────────
ARG ZLIB_VERSION=1.3.1
RUN curl -fsSL \
    "https://github.com/madler/zlib/releases/download/v${ZLIB_VERSION}/zlib-${ZLIB_VERSION}.tar.gz" \
    | tar xz

RUN cd zlib-${ZLIB_VERSION} \
    && emcmake cmake -B build-em \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/emsdk/sysroot/usr \
        -DBUILD_SHARED_LIBS=OFF \
        -DCMAKE_C_FLAGS="-fPIC" \
    && cmake --build build-em -j$(nproc) \
    && cmake --install build-em

# zlib cmake doesn't generate a .pc file; create one so pkg-config can find it.
RUN mkdir -p /emsdk/sysroot/usr/lib/pkgconfig \
    && cat > /emsdk/sysroot/usr/lib/pkgconfig/zlib.pc << 'EOF'
prefix=/emsdk/sysroot/usr
Name: zlib
Description: zlib compression library
Version: 1.3.1
Libs: -L${prefix}/lib -lz
Cflags: -I${prefix}/include
EOF

# ── libpng (required by leptonica PNG support) ────────────────────────────────
ARG LIBPNG_VERSION=1.6.43
RUN curl -fsSL \
    "https://github.com/glennrp/libpng/archive/refs/tags/v${LIBPNG_VERSION}.tar.gz" \
    | tar xz

RUN cd libpng-${LIBPNG_VERSION} \
    && emcmake cmake -B build-em \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/emsdk/sysroot/usr \
        -DBUILD_SHARED_LIBS=OFF \
        -DPNG_SHARED=OFF \
        -DPNG_STATIC=ON \
        -DPNG_TESTS=OFF \
        -DZLIB_LIBRARY=/emsdk/sysroot/usr/lib/libz.a \
        -DZLIB_INCLUDE_DIR=/emsdk/sysroot/usr/include \
        -DCMAKE_C_FLAGS="-fPIC -fwasm-exceptions" \
    && cmake --build build-em -j$(nproc) \
    && cmake --install build-em \
    && ln -sf /emsdk/sysroot/usr/lib/libpng16.a /emsdk/sysroot/usr/lib/libpng.a

# ── leptonica ────────────────────────────────────────────────────────────────
ARG LEPTONICA_VERSION=1.84.1
RUN curl -fsSL \
    "https://github.com/DanBloomberg/leptonica/releases/download/${LEPTONICA_VERSION}/leptonica-${LEPTONICA_VERSION}.tar.gz" \
    | tar xz

RUN cd leptonica-${LEPTONICA_VERSION} \
    && emcmake cmake -B build-em \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/emsdk/sysroot/usr \
        -DBUILD_SHARED_LIBS=OFF \
        -DENABLE_GIF=OFF \
        -DENABLE_JPEG=OFF \
        -DENABLE_OPENJPEG=OFF \
        -DENABLE_PNG=ON \
        -DENABLE_TIFF=OFF \
        -DENABLE_WEBP=OFF \
        -DENABLE_ZLIB=ON \
        -DZLIB_LIBRARY=/emsdk/sysroot/usr/lib/libz.a \
        -DZLIB_INCLUDE_DIR=/emsdk/sysroot/usr/include \
        -DPNG_LIBRARY=/emsdk/sysroot/usr/lib/libpng.a \
        -DPNG_PNG_INCLUDE_DIR=/emsdk/sysroot/usr/include \
        -DCMAKE_C_FLAGS="-fPIC -fwasm-exceptions" \
    && cmake --build build-em -j$(nproc) \
    && cmake --install build-em \
    && ln -sf /emsdk/sysroot/usr/lib/pkgconfig/lept_Release.pc \
              /emsdk/sysroot/usr/lib/pkgconfig/lept.pc

# ── tesseract ────────────────────────────────────────────────────────────────
ARG TESSERACT_VERSION=5.3.4
RUN curl -fsSL \
    "https://github.com/tesseract-ocr/tesseract/archive/refs/tags/${TESSERACT_VERSION}.tar.gz" \
    | tar xz

RUN cd tesseract-${TESSERACT_VERSION} \
    && emcmake cmake -B build-em \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/emsdk/sysroot/usr \
        -DBUILD_SHARED_LIBS=OFF \
        -DBUILD_TRAINING_TOOLS=OFF \
        -DDISABLE_CURL=ON \
        -DDISABLE_ARCHIVE=ON \
        -DDISABLE_LEGACY_ENGINE=ON \
        -DGRAPHICS_DISABLED=ON \
        -DLeptonica_DIR=/emsdk/sysroot/usr/lib/cmake/leptonica \
        -DCMAKE_C_FLAGS="-fPIC -fwasm-exceptions" \
        -DCMAKE_CXX_FLAGS="-fPIC -fwasm-exceptions" \
    && cmake --build build-em -j$(nproc) \
    && cmake --install build-em

# ── eng.traineddata ───────────────────────────────────────────────────────────
# Fetch the fast (4 MB) model — small enough to ship with the WASM module.
RUN mkdir -p /tessdata \
    && curl -fsSL \
    "https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata" \
    -o /tessdata/eng.traineddata

WORKDIR /app

# The actual build is run by the host script that mounts the repo here.
# Default CMD shows usage.
CMD ["bash", "-c", \
    "echo 'Run: docker run --rm -v $(pwd):/app ios-screen-time-wasm-builder scripts/build-wasm-emscripten.sh'"]
