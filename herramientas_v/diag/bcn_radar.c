/* Radar y mapa de Barcelona, plugin de ScriptHookV (bcn_radar.asi).
 *
 * El radar del juego solo tiene Los Santos (sin el mapa del juego, mar). Este plugin lo esconde y pinta el plano
 * de Barcelona que hace radar_v.py (DLC bcnradar: texturas bcnradar_<bx>_<by> de 2 m/px y bcnradar_mapa):
 *   - radar abajo a la izquierda, girando con la cámara, con la flecha del jugador, el norte y la vida/blindaje;
 *     se aleja al ir rápido en un vehículo;
 *   - el mapa del menú de pausa (ESC) es el del juego con las texturas de mapa_pausa_v.py (no es de aquí);
 *   - tecla M: mapa grande (rueda: zoom; arrastrar con el ratón o WASD/flechas: mover; clic derecho o Intro: ir
 *     a ese punto; M o Retroceso: cerrar).
 * El radar se dibuja en celdas pequeñas (un trozo de textura cada una, girado): así queda recortado en su marco.
 * Lee bcn_radar.txt (rejilla y bloques que existen) de la carpeta del juego; escribe bcn_radar.log.
 * Compilar: zig cc -target x86_64-windows-gnu -shared -O2 -o bcn_radar.asi bcn_radar.c
 */
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>

static void (*sh_init)(uint64_t);
static void (*sh_push)(uint64_t);
static uint64_t *(*sh_call)(void);
static void (*sh_wait)(DWORD);
static void (*sh_register)(HMODULE, void (*)(void));
static void (*sh_unregister)(HMODULE);
static FILE *registro;

static void pi(int64_t v) { sh_push((uint64_t)v); }
static void pf(float f) { uint64_t v = 0; memcpy(&v, &f, sizeof f); sh_push(v); }
static void pp(const void *p) { sh_push((uint64_t)(uintptr_t)p); }
static uint64_t *llamar(void) { return sh_call(); }
static float rf(uint64_t *r, int i) { float f; memcpy(&f, &r[i], sizeof f); return f; }

static void apuntar(const char *texto)
{
    if (!registro) return;
    SYSTEMTIME t;
    GetLocalTime(&t);
    fprintf(registro, "%02d:%02d:%02d %s\n", t.wHour, t.wMinute, t.wSecond, texto);
    fflush(registro);
}

/* ---- funciones del juego ---- */
static int ped_jugador(void) { sh_init(0xD80958FC74E988A6ULL); return (int)*llamar(); }
static void coords(int ent, float *x, float *y, float *z)
{
    sh_init(0x3FEF770D40960D5AULL); pi(ent); pi(1); uint64_t *r = llamar();
    *x = rf(r, 0); *y = rf(r, 1); *z = rf(r, 2);
}
static float rumbo(int ent) { sh_init(0xE83D4F9BA2A38914ULL); pi(ent); return rf(llamar(), 0); }
static float rumbo_camara(void) { sh_init(0x837765A25378F0BBULL); pi(2); return rf(llamar(), 2); }
static float velocidad(int ent) { sh_init(0xD5037BA82E12416FULL); pi(ent); return rf(llamar(), 0); }
static int en_vehiculo(int ped) { sh_init(0x997ABD671D25CA0BULL); pi(ped); pi(0); return (int)(*llamar() & 1); }
static int vehiculo(int ped) { sh_init(0x9A9112A0FE9A4713ULL); pi(ped); pi(0); return (int)*llamar(); }
static int vida(int ent) { sh_init(0xEEF059FAD016D209ULL); pi(ent); return (int)*llamar(); }
static int vida_max(int ent) { sh_init(0x15D757606D170C3CULL); pi(ent); return (int)*llamar(); }
static int blindaje(int ped) { sh_init(0x9483AF821605B1D8ULL); pi(ped); return (int)*llamar(); }
static void mostrar_radar(int si) { sh_init(0xA0EBB943C300E693ULL); pi(si); llamar(); }
static int menu_pausa(void) { sh_init(0xB0034A223497FFCBULL); return (int)(*llamar() & 1); }
static int hud_oculto(void) { sh_init(0xA86478C6958735C5ULL); return (int)(*llamar() & 1); }
static int cargando(void) { sh_init(0x10D0A8F259E93EC9ULL); return (int)(*llamar() & 1); }
static int pantalla_negra(void) { sh_init(0xB16FCE9DDC7BA182ULL); return (int)(*llamar() & 1); }
static int en_escena(void) { sh_init(0xD3C2E180A40F031EULL); return (int)(*llamar() & 1); } /* IS_CUTSCENE_PLAYING */
static float aspecto(void) { sh_init(0xF1307EF624A80D87ULL); pi(0); return rf(llamar(), 0); }
static void pedir_ytd(const char *n) { sh_init(0xDFA2EF8E04127DD5ULL); pp(n); pi(0); llamar(); }
static int ytd_listo(const char *n) { sh_init(0x0145F696AAAAD2E4ULL); pp(n); return (int)(*llamar() & 1); }
static void soltar_ytd(const char *n) { sh_init(0xBE2CACCF5A8AA805ULL); pp(n); llamar(); }
static void sprite_c(const char *d, const char *t, float x, float y, float w, float h, float giro,
                     int r, int g, int b, int a)
{
    sh_init(0xE7FFAE5EBF23D890ULL); pp(d); pp(t); pf(x); pf(y); pf(w); pf(h); pf(giro);
    pi(r); pi(g); pi(b); pi(a); pi(0); llamar();
}
static void sprite(const char *d, const char *t, float x, float y, float w, float h, float giro, int a)
{
    sprite_c(d, t, x, y, w, h, giro, 255, 255, 255, a);
}
/* SET_SCRIPT_GFX_DRAW_ORDER: lo de cada capa se dibuja después que lo de las capas más bajas
   (si no, el juego no respeta el orden de las llamadas: el marco y la flecha quedaban debajo de las celdas) */
static void orden(int capa) { sh_init(0x61BB1D9B3A95D802ULL); pi(capa); llamar(); }
/* rectángulo liso con la textura blanca teñida (los DRAW_RECT van en otra lista y salen por debajo) */
static void liso(float x, float y, float w, float h, int r, int g, int b, int a)
{
    sprite_c("bcnradar_mapa", "blanco", x, y, w, h, 0, r, g, b, a);
}
/* DRAW_SPRITE_ARX_WITH_UV / DRAW_SPRITE_WITH_UV: un trozo (u1,v1)-(u2,v2) de la textura */
static uint64_t HASH_UV = 0x95812F9B26074726ULL;
static void sprite_uv(const char *d, const char *t, float x, float y, float w, float h,
                      float u1, float v1, float u2, float v2, float giro, int a)
{
    sh_init(HASH_UV); pp(d); pp(t); pf(x); pf(y); pf(w); pf(h); pf(u1); pf(v1); pf(u2); pf(v2); pf(giro);
    pi(255); pi(255); pi(255); pi(a); pi(0); llamar();
}
static void sin_controles(void) { sh_init(0x5F4B6931816E599BULL); pi(0); llamar(); }
static int control_ya(int c) { sh_init(0x91AEF906BCA88877ULL); pi(0); pi(c); return (int)(*llamar() & 1); }
static int control(int c) { sh_init(0xE2587F8CBBD87B1DULL); pi(0); pi(c); return (int)(*llamar() & 1); }
static float control_valor(int c) { sh_init(0x11E65974A982637CULL); pi(0); pi(c); return rf(llamar(), 0); }
static void cursor_visible(void) { sh_init(0xAAE7CE1D63167423ULL); llamar(); }
static void texto_a(const char *s, float x, float y, float escala, int just);
static void texto(const char *s, float x, float y, float escala, int centrado)
{
    texto_a(s, x, y, escala, centrado ? 0 : 1);
}
/* just: 0 centrado, 1 izquierda, 2 derecha (x es el borde derecho) */
static void texto_a(const char *s, float x, float y, float escala, int just)
{
    if (just == 2) {
        sh_init(0x4E096588B13FFECAULL); pi(2); llamar();                  /* SET_TEXT_JUSTIFICATION */
        sh_init(0x63145D9C883A1A70ULL); pf(0.0f); pf(x); llamar();       /* SET_TEXT_WRAP */
    }
    int centrado = just == 0;
    sh_init(0x66E0276CC5F6B9DAULL); pi(4); llamar();                      /* SET_TEXT_FONT */
    sh_init(0x07C837F9A01C34C9ULL); pf(escala); pf(escala); llamar();   /* SET_TEXT_SCALE */
    sh_init(0xBE6B23FFA53FB442ULL); pi(255); pi(255); pi(255); pi(255); llamar(); /* SET_TEXT_COLOUR */
    sh_init(0x2513DFB0FB8400FEULL); llamar();                            /* SET_TEXT_OUTLINE */
    sh_init(0xC02F4DBFB51D988BULL); pi(centrado); llamar();             /* SET_TEXT_CENTRE */
    sh_init(0x25FBB336DF1804CBULL); pp("STRING"); llamar();             /* BEGIN_TEXT_COMMAND_DISPLAY_TEXT */
    sh_init(0x6C188BE134E074AAULL); pp(s); llamar();                    /* ADD_TEXT_COMPONENT_SUBSTRING_... */
    sh_init(0xCD015E5BB0D96A57ULL); pf(x); pf(y); pi(0); llamar();     /* END_TEXT_COMMAND_DISPLAY_TEXT */
}
static void mover(int ent, float x, float y, float z)
{
    sh_init(0x06843DA7060A026BULL); pi(ent); pf(x); pf(y); pf(z); pi(0); pi(0); pi(0); pi(1); llamar();
}
static void congelar(int ent, int si) { sh_init(0x428CA6DBD1094446ULL); pi(ent); pi(si); llamar(); }
static void pedir_colision(float x, float y, float z) { sh_init(0x07503F7948F491A7ULL); pf(x); pf(y); pf(z); llamar(); }
static int suelo(float x, float y, float *z)
{
    sh_init(0xC906A7DAB05C8D2BULL); pf(x); pf(y); pf(1000.0f); pp(z); pi(0); return (int)(*llamar() & 1);
}

/* ---- rejilla del plano (bcn_radar.txt) ---- */
static float X0 = -4608, Y0 = -8192, BLOQUE = 2048, TESELA = 512;
static int NBX = 7, NBY = 9;
static unsigned char hay[64][64];
static char cargado[64][64];      /* 0 nada, 1 pedido */
static DWORD usado[64][64];       /* último uso (ms) */
static int mapa_listo;

static void leer_rejilla(void)
{
    FILE *f = fopen("bcn_radar.txt", "r");
    if (!f) { apuntar("falta bcn_radar.txt"); return; }
    if (fscanf(f, "%f %f %f %f %d %d", &X0, &Y0, &BLOQUE, &TESELA, &NBX, &NBY) != 6) { fclose(f); return; }
    int bx, by, n = 0;
    while (fscanf(f, "%d %d", &bx, &by) == 2)
        if (bx >= 0 && by >= 0 && bx < 64 && by < 64) { hay[bx][by] = 1; n++; }
    fclose(f);
    char t[80];
    snprintf(t, sizeof t, "rejilla: %d bloques", n);
    apuntar(t);
}

static void nombre_bloque(char *s, int bx, int by) { sprintf(s, "bcnradar_%d_%d", bx, by); }

/* ¿se puede dibujar el bloque? Lo pide mientras no esté: el juego puede descargarlo para hacer sitio (al ir
   deprisa se cargan muchas cosas) y, si solo se pedía una vez, el radar se quedaba con el plano general, borroso */
static char listo_antes[64][64];
static int perdidos;
static int bloque_listo(int bx, int by)
{
    if (bx < 0 || by < 0 || bx >= NBX || by >= NBY || !hay[bx][by]) return 0;
    char n[32];
    nombre_bloque(n, bx, by);
    usado[bx][by] = GetTickCount();
    cargado[bx][by] = 1;
    int ok = ytd_listo(n);
    if (!ok) {
        pedir_ytd(n);
        if (listo_antes[bx][by]) { listo_antes[bx][by] = 0; perdidos++; }
    } else listo_antes[bx][by] = 1;
    return ok;
}

/* suelta los bloques lejanos (a más de un bloque del jugador) que llevan 30 s sin usarse */
static float jug_x, jug_y;
static void soltar_viejos(void)
{
    DWORD ahora = GetTickCount();
    int pbx = (int)floorf((jug_x - X0) / BLOQUE), pby = (int)floorf((jug_y - Y0) / BLOQUE);
    for (int bx = 0; bx < NBX; bx++)
        for (int by = 0; by < NBY; by++)
            if (cargado[bx][by] && ahora - usado[bx][by] > 30000 && (abs(bx - pbx) > 1 || abs(by - pby) > 1)) {
                char n[32];
                nombre_bloque(n, bx, by);
                soltar_ytd(n);
                cargado[bx][by] = 0;
                listo_antes[bx][by] = 0;
            }
}

#define MAR_R 38
#define MAR_G 64
#define MAR_B 90

/* ---- nombre de la calle (bcn_calles.bin, de radar_v.py) ---- */
static char **nombres;
static int n_nombres, n_tramos, m_ancho, m_alto;
static float *tramo;       /* x0 y0 x1 y1 */
static int *tramo_nom, *muni;
static float m_x0, m_y0, m_paso;
#define CELDA_C 64.0f
static int c_ancho, c_alto, *c_ini, *c_lista;

static void leer_calles(void)
{
    FILE *f = fopen("bcn_calles.bin", "rb");
    if (!f) { apuntar("falta bcn_calles.bin"); return; }
    fseek(f, 0, SEEK_END);
    long t = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *b = malloc(t);
    if (!b || fread(b, 1, t, f) != (size_t)t || memcmp(b, "BCNC", 4)) { fclose(f); return; }
    fclose(f);
    memcpy(&n_nombres, b + 4, 4); memcpy(&n_tramos, b + 8, 4);
    memcpy(&m_x0, b + 12, 4); memcpy(&m_y0, b + 16, 4); memcpy(&m_paso, b + 20, 4);
    memcpy(&m_ancho, b + 24, 4); memcpy(&m_alto, b + 28, 4);
    char *p = b + 32;
    nombres = malloc(sizeof(char *) * n_nombres);
    for (int i = 0; i < n_nombres; i++) { nombres[i] = p; p += strlen(p) + 1; }
    tramo = (float *)p; p += 16L * n_tramos;
    tramo_nom = (int *)p; p += 4L * n_tramos;
    muni = (int *)p;
    /* índice: tramos de cada cuadro de 64 m (por su caja) */
    c_ancho = (int)(m_ancho * m_paso / CELDA_C) + 1; c_alto = (int)(m_alto * m_paso / CELDA_C) + 1;
    int nc = c_ancho * c_alto;
    c_ini = calloc(nc + 1, sizeof(int));
    for (int pasada = 0; pasada < 2; pasada++) {
        int *lleno = pasada ? calloc(nc, sizeof(int)) : NULL;
        for (int k = 0; k < n_tramos; k++) {
            float *q = tramo + 4 * k;
            int i0 = (int)((fminf(q[0], q[2]) - m_x0) / CELDA_C), i1 = (int)((fmaxf(q[0], q[2]) - m_x0) / CELDA_C);
            int j0 = (int)((fminf(q[1], q[3]) - m_y0) / CELDA_C), j1 = (int)((fmaxf(q[1], q[3]) - m_y0) / CELDA_C);
            for (int i = i0 < 0 ? 0 : i0; i <= i1 && i < c_ancho; i++)
                for (int j = j0 < 0 ? 0 : j0; j <= j1 && j < c_alto; j++) {
                    int c = j * c_ancho + i;
                    if (!pasada) c_ini[c + 1]++;
                    else c_lista[c_ini[c] + lleno[c]++] = k;
                }
        }
        if (!pasada) {
            for (int c = 0; c < nc; c++) c_ini[c + 1] += c_ini[c];
            c_lista = malloc(sizeof(int) * (c_ini[nc] + 1));
        } else free(lleno);
    }
    char m[80];
    snprintf(m, sizeof m, "calles: %d nombres, %d tramos", n_nombres, n_tramos);
    apuntar(m);
}

/* nombre de la calle más cercana (a menos de 30 m) y del municipio */
static const char *calle_en(float x, float y, const char **mun)
{
    *mun = NULL;
    if (!tramo) return NULL;
    int mi = (int)((x - m_x0) / m_paso), mj = (int)((y - m_y0) / m_paso);
    if (mi >= 0 && mj >= 0 && mi < m_ancho && mj < m_alto) {
        int k = muni[mj * m_ancho + mi];
        if (k >= 0 && k < n_nombres) *mun = nombres[k];
    }
    int ci = (int)((x - m_x0) / CELDA_C), cj = (int)((y - m_y0) / CELDA_C);
    float mejor = 30.0f * 30.0f;
    int cual = -1;
    for (int i = ci - 1; i <= ci + 1; i++)
        for (int j = cj - 1; j <= cj + 1; j++) {
            if (i < 0 || j < 0 || i >= c_ancho || j >= c_alto) continue;
            int c = j * c_ancho + i;
            for (int l = c_ini[c]; l < c_ini[c + 1]; l++) {
                float *q = tramo + 4 * c_lista[l];
                float dx = q[2] - q[0], dy = q[3] - q[1], L = dx * dx + dy * dy;
                float u = L > 0 ? ((x - q[0]) * dx + (y - q[1]) * dy) / L : 0;
                u = u < 0 ? 0 : u > 1 ? 1 : u;
                float ex = q[0] + u * dx - x, ey = q[1] + u * dy - y, d = ex * ex + ey * ey;
                if (tramo_nom[c_lista[l]] & 0x40000000) { d = sqrtf(d) + 15.0f; d *= d; }  /* puente: arriba */
                if (d < mejor) { mejor = d; cual = c_lista[l]; }
            }
        }
    return cual >= 0 ? nombres[tramo_nom[cual] & 0x3FFFFFFF] : NULL;
}

static void dibujar_calle(int ped)
{
    static DWORD ultimo;
    static const char *calle, *mun;
    if (GetTickCount() - ultimo > 300) {
        float x, y, z;
        coords(ped, &x, &y, &z);
        calle = calle_en(x, y, &mun);
        ultimo = GetTickCount();
    }
    orden(4);
    if (calle) texto_a(calle, 0.985f, 0.895f, 0.55f, 2);
    if (mun) texto_a(mun, 0.985f, 0.935f, 0.40f, 2);
}

/* ---- radar ---- */
static float zoom_suave = 240.0f;   /* metros de alto que se ven */

static void dibujar_radar(int ped)
{
    float a = aspecto();
    if (a < 0.5f || a > 5.0f) a = 16.0f / 9.0f;
    /* marco en unidades de alto de pantalla; x en fracción del ancho = unidades / a */
    const float H = 0.185f, W = 0.27f, IZQ = 0.028f, ABAJO = 0.058f;
    float cx = (IZQ + W / 2) / a, cy = 1.0f - ABAJO - H / 2;
    float px, py, pz;
    coords(ped, &px, &py, &pz);
    int coche = en_vehiculo(ped);
    float v = coche ? velocidad(vehiculo(ped)) : 0.0f;
    float objetivo = 240.0f + (v > 40 ? 40 : v) * 8.0f;
    zoom_suave += (objetivo - zoom_suave) * 0.03f;
    float S = H / zoom_suave;              /* unidades de alto por metro */
    float h = rumbo_camara() * 3.14159265f / 180.0f;
    float ch = cosf(h), sh = sinf(h);
    /* el jugador algo por debajo del centro, como en el radar del juego */
    float jy = cy + H * 0.12f;
    /* tamaño de celda: ~9 px en 1080p */
    float C = 4;
    while (C * S * 1080.0f < 8.0f && C < 128) C *= 2;

    if (!mapa_listo) return;
    /* los bloques de alrededor (1 km) y los de delante (hasta 2,5 km según la velocidad) se piden antes de que
       entren en el marco */
    jug_x = px; jug_y = py;
    {
        float vx = 0, vy = 0;
        if (coche) { sh_init(0x4805D2B1D8CF94A9ULL); pi(vehiculo(ped)); uint64_t *r = llamar(); vx = rf(r, 0); vy = rf(r, 1); }
        for (int i = -1; i <= 1; i++)
            for (int j = -1; j <= 1; j++) {
                bloque_listo((int)floorf((px + i * 1000.0f - X0) / BLOQUE), (int)floorf((py + j * 1000.0f - Y0) / BLOQUE));
                for (int k = 1; k <= 3; k++) {   /* hacia donde va: a 20, 40 y 60 s */
                    float ex = px + vx * 20.0f * k + i * 600.0f, ey = py + vy * 20.0f * k + j * 600.0f;
                    if (vx * vx + vy * vy > 25.0f && fabsf(vx * 20.0f * k) < 2500 && fabsf(vy * 20.0f * k) < 2500)
                        bloque_listo((int)floorf((ex - X0) / BLOQUE), (int)floorf((ey - Y0) / BLOQUE));
                }
            }
    }
    int celdas = 0;
    orden(1);
    sprite("bcnradar_mapa", "mar", cx, cy, W / a, H, 0, 235);
    /* zona del mundo que cae en el marco (caja del rectángulo girado) */
    float medio = sqrtf(W * W + H * H) / S;  /* de sobra */
    float wx0 = px - medio, wx1 = px + medio, wy0 = py - medio, wy1 = py + medio;
    float lado = C * S, mitad = lado * 0.5f;
    for (float gx = floorf(wx0 / C) * C; gx < wx1; gx += C) {
        for (float gy = floorf(wy0 / C) * C; gy < wy1; gy += C) {
            float dx = gx + C / 2 - px, dy = gy + C / 2 - py;
            float sr = dx * ch + dy * sh, su = -dx * sh + dy * ch;   /* derecha y adelante de la cámara */
            float ux = sr * S, uy = -su * S;                         /* en unidades de alto */
            float sx = cx * a + ux, sy = jy + uy;
            if (sx < (cx * a - W / 2) - mitad || sx > (cx * a + W / 2) + mitad ||
                sy < (cy - H / 2) - mitad || sy > (cy + H / 2) + mitad)
                continue;
            int bx = (int)floorf((gx - X0) / BLOQUE), by = (int)floorf((gy - Y0) / BLOQUE);
            float bx0 = X0 + bx * BLOQUE, by0 = Y0 + by * BLOQUE;
            celdas++;
            if (!bloque_listo(bx, by)) {
                /* aún no ha llegado el bloque fino: el plano general (siempre cargado), no el azul del mar */
                if (bx < 0 || by < 0 || bx >= NBX || by >= NBY || !hay[bx][by]) continue;
                char t[24];
                sprintf(t, "m_%d_%d", bx, by);
                float u1 = (gx - bx0) / BLOQUE, v1 = 1.0f - (gy + C - by0) / BLOQUE;
                sprite_uv("bcnradar_mapa", t, sx / a, sy, (lado * 1.04f) / a, lado * 1.04f, u1, v1,
                          u1 + C / BLOQUE, v1 + C / BLOQUE, h * 180.0f / 3.14159265f, 255);
                continue;
            }
            int i = (int)floorf((gx - bx0) / TESELA), j = (int)floorf((gy - by0) / TESELA);
            float tx0 = bx0 + i * TESELA, ty0 = by0 + j * TESELA;
            char d[32], t[8];
            nombre_bloque(d, bx, by);
            sprintf(t, "t%d%d", i, j);
            float u1 = (gx - tx0) / TESELA, v1 = 1.0f - (gy + C - ty0) / TESELA;
            float u2 = u1 + C / TESELA, v2 = v1 + C / TESELA;
            const float m = 0.5f / 256.0f;   /* medio texel: en el borde la textura se repite y mezclaba */
            if (u1 < m) u1 = m;
            if (v1 < m) v1 = m;
            if (u2 > 1 - m) u2 = 1 - m;
            if (v2 > 1 - m) v2 = 1 - m;
            /* un pelín más grande para que no se vean juntas */
            sprite_uv(d, t, sx / a, sy, (lado * 1.04f) / a, lado * 1.04f, u1, v1, u2, v2,
                      h * 180.0f / 3.14159265f, 255);
        }
    }
    {   /* para ver en el registro si faltan bloques o hay demasiadas celdas */
        static DWORD t_reg; static int max_celdas, perd_antes;
        if (celdas > max_celdas) max_celdas = celdas;
        if (GetTickCount() - t_reg > 10000) {
            if (perdidos != perd_antes || max_celdas > 0) {
                char t[96];
                snprintf(t, sizeof t, "radar: hasta %d celdas, C %.0f m, bloques perdidos %d", max_celdas, C, perdidos);
                apuntar(t);
            }
            t_reg = GetTickCount(); max_celdas = 0; perd_antes = perdidos;
        }
    }
    /* marco: tapa lo que sale de las celdas del borde */
    orden(2);
    float g = mitad * 1.5f + 0.004f;
    int mr = 12, mg = 14, mb = 14, ma = 255;
    liso(cx, cy - H / 2 - g / 2, (W + 2 * g) / a, g, mr, mg, mb, ma);
    liso(cx, cy + H / 2 + g / 2, (W + 2 * g) / a, g, mr, mg, mb, ma);
    liso(cx - (W / 2 + g / 2) / a, cy, g / a, H, mr, mg, mb, ma);
    liso(cx + (W / 2 + g / 2) / a, cy, g / a, H, mr, mg, mb, ma);
    /* jugador */
    orden(3);
    {
        float f = 0.022f;
        sprite("bcnradar_mapa", "flecha", cx, jy, f / a, f, (h * 180.0f / 3.14159265f) - rumbo(ped), 255);
    }
    /* norte: en el borde del marco, en la dirección del norte */
    {
        float nx = sh, ny = -ch;   /* el norte (0,1) en pantalla: derecha = sin h, arriba = cos h */
        float hx = W / 2 - 0.012f, hy = H / 2 - 0.012f;
        float k = 1e9f;
        if (fabsf(nx) > 1e-4f) k = fminf(k, hx / fabsf(nx));
        if (fabsf(ny) > 1e-4f) k = fminf(k, hy / fabsf(ny));
        /* desde el centro del marco, no desde el jugador */
        texto("N", (cx * a + nx * k) / a, cy + ny * k - 0.014f, 0.32f, 1);
    }
    /* vida y blindaje debajo, como el juego */
    float bh = 0.009f, by_ = cy + H / 2 + g + 0.004f + bh / 2;
    int vm = vida_max(ped), vv = vida(ped);
    float fv = vm > 100 ? (float)(vv - 100) / (float)(vm - 100) : 0;
    if (fv < 0) fv = 0;
    if (fv > 1) fv = 1;
    float fa = blindaje(ped) / 100.0f;
    if (fa > 1) fa = 1;
    float ancho_v = (W + 2 * g) * 0.5f - 0.002f;
    float x_v = cx - (W / 2 + g) / a + ancho_v / 2 / a;
    float x_a = cx + (W / 2 + g) / a - ancho_v / 2 / a;
    orden(2);
    liso(x_v, by_, ancho_v / a, bh, 30, 60, 30, 200);
    liso(x_a, by_, ancho_v / a, bh, 25, 45, 70, 200);
    orden(3);
    if (fv > 0) liso(x_v - ancho_v * (1 - fv) / 2 / a, by_, ancho_v * fv / a, bh, 90, 180, 90, 230);
    if (fa > 0) liso(x_a - ancho_v * (1 - fa) / 2 / a, by_, ancho_v * fa / a, bh, 90, 150, 220, 230);
    orden(4);
}

/* ---- mapa grande (M) ---- */
static int mapa_abierto;
static float mx, my, mzoom = 9000.0f;   /* centro y metros de alto que se ven */
static float arr_x, arr_y, arr_mx, arr_my;
static int arrastrando;

static void ir_a(int ped, float x, float y)
{
    int ent = en_vehiculo(ped) ? vehiculo(ped) : ped;
    float z = 0;
    congelar(ent, 1);
    mover(ent, x, y, 300.0f);
    for (int i = 0; i < 100; i++) {
        pedir_colision(x, y, 100.0f);
        if (i == 20) mover(ent, x, y, 80.0f);
        if (suelo(x, y, &z) && z > -50.0f) break;
        sh_wait(50);
    }
    if (!suelo(x, y, &z)) z = 60.0f;
    mover(ent, x, y, z + 1.0f);
    congelar(ent, 0);
    char t[96];
    snprintf(t, sizeof t, "ir a %.0f %.0f (suelo %.1f)", x, y, z);
    apuntar(t);
}

static void dibujar_mapa(int ped)
{
    float a = aspecto();
    if (a < 0.5f || a > 5.0f) a = 16.0f / 9.0f;
    sin_controles();
    cursor_visible();
    /* rueda: zoom hacia el cursor */
    float cux = control_valor(239), cuy = control_valor(240);   /* cursor 0..1 */
    float S = 1.0f / mzoom;
    float wx = mx + (cux - 0.5f) * a / S, wy = my - (cuy - 0.5f) / S;  /* punto bajo el cursor */
    float z = mzoom;
    if (control_ya(241)) z *= 0.8f;
    if (control_ya(242)) z *= 1.25f;
    if (GetAsyncKeyState(VK_PRIOR) & 0x8000) z *= 0.97f;
    if (GetAsyncKeyState(VK_NEXT) & 0x8000) z *= 1.03f;
    if (z < 250) z = 250;
    if (z > 20000) z = 20000;
    if (z != mzoom) {   /* el punto bajo el cursor no se mueve */
        mzoom = z; S = 1.0f / mzoom;
        mx = wx - (cux - 0.5f) * a / S; my = wy + (cuy - 0.5f) / S;
    }
    float paso = mzoom * 0.012f;
    if (GetAsyncKeyState('W') & 0x8000 || GetAsyncKeyState(VK_UP) & 0x8000) my += paso;
    if (GetAsyncKeyState('S') & 0x8000 || GetAsyncKeyState(VK_DOWN) & 0x8000) my -= paso;
    if (GetAsyncKeyState('A') & 0x8000 || GetAsyncKeyState(VK_LEFT) & 0x8000) mx -= paso;
    if (GetAsyncKeyState('D') & 0x8000 || GetAsyncKeyState(VK_RIGHT) & 0x8000) mx += paso;
    if (control(24)) {          /* arrastrar con el botón izquierdo */
        if (!arrastrando) { arrastrando = 1; arr_x = cux; arr_y = cuy; arr_mx = mx; arr_my = my; }
        mx = arr_mx - (cux - arr_x) * a / S;
        my = arr_my + (cuy - arr_y) / S;
    } else arrastrando = 0;

    if (!mapa_listo) return;
    orden(5);
    sprite("bcnradar_mapa", "mar", 0.5f, 0.5f, 1.0f, 1.0f, 0, 255);
    orden(6);
    /* zona visible */
    float vx0 = mx - 0.5f * a / S, vx1 = mx + 0.5f * a / S, vy0 = my - 0.5f / S, vy1 = my + 0.5f / S;
    int bx0 = (int)floorf((vx0 - X0) / BLOQUE), bx1 = (int)floorf((vx1 - X0) / BLOQUE);
    int by0 = (int)floorf((vy0 - Y0) / BLOQUE), by1 = (int)floorf((vy1 - Y0) / BLOQUE);
    float px_por_m = S * 1080.0f;
    int detalle = px_por_m * 8.0f > 1.6f;   /* el plano general (8 m/px) ya se vería borroso */
    for (int bx = bx0; bx <= bx1; bx++) {
        for (int by = by0; by <= by1; by++) {
            if (bx < 0 || by < 0 || bx >= NBX || by >= NBY || !hay[bx][by]) continue;
            float cxw = X0 + (bx + 0.5f) * BLOQUE, cyw = Y0 + (by + 0.5f) * BLOQUE;
            float sx = 0.5f + (cxw - mx) * S / a, sy = 0.5f - (cyw - my) * S;
            int fino = detalle && bloque_listo(bx, by);
            if (!fino && mapa_listo) {
                char t[24];
                sprintf(t, "m_%d_%d", bx, by);
                const float m = 0.5f / 256.0f;
                sprite_uv("bcnradar_mapa", t, sx, sy, BLOQUE * S * 1.002f / a, BLOQUE * S * 1.002f, m, m, 1 - m, 1 - m, 0, 255);
            }
            if (fino) {
                char d[32];
                nombre_bloque(d, bx, by);
                int n = (int)(BLOQUE / TESELA);
                for (int i = 0; i < n; i++)
                    for (int j = 0; j < n; j++) {
                        float tx = X0 + bx * BLOQUE + (i + 0.5f) * TESELA, ty = Y0 + by * BLOQUE + (j + 0.5f) * TESELA;
                        char t[8];
                        sprintf(t, "t%d%d", i, j);
                        const float m = 0.5f / 256.0f;
                        sprite_uv(d, t, 0.5f + (tx - mx) * S / a, 0.5f - (ty - my) * S, TESELA * S * 1.004f / a,
                                  TESELA * S * 1.004f, m, m, 1 - m, 1 - m, 0, 255);
                    }
            }
        }
    }
    /* jugador */
    orden(7);
    float px, py, pz;
    coords(ped, &px, &py, &pz);
    {
        float f = 0.03f;
        sprite("bcnradar_mapa", "flecha", 0.5f + (px - mx) * S / a, 0.5f - (py - my) * S, f / a, f, -rumbo(ped), 255);
    }
    /* cursor: cruz */
    liso(cux, cuy, 0.012f / a, 0.0015f, 255, 255, 255, 220);
    liso(cux, cuy, 0.0015f / a, 0.012f, 255, 255, 255, 220);
    liso(0.5f, 0.975f, 1.0f, 0.05f, 0, 0, 0, 160);
    orden(8);
    texto("Rueda: zoom   Arrastrar o WASD: mover   Clic derecho o Intro: ir aqui   M o Retroceso: cerrar",
          0.5f, 0.960f, 0.29f, 1);
    if (control_ya(25) || (GetAsyncKeyState(VK_RETURN) & 1)) {
        mapa_abierto = 0;
        ir_a(ped, wx, wy);
    }
}

/* ---- bucle ---- */
static int tecla_m_antes;

static void principal(void)
{
    apuntar("bcn_radar en marcha");
    leer_rejilla();
    leer_calles();
    DWORD ultimo_soltar = GetTickCount();
    int avisado = 0;
    /* prueba sin nadie delante: con bcn_radar_auto.txt abre el mapa solo y hace capturas de Steam (F12) */
    FILE *fa = fopen("bcn_radar_auto.txt", "r");
    int automatico = fa != NULL, paso = 0;
    if (fa) fclose(fa);
    DWORD t_listo = 0;
    for (;;) {
        sh_wait(0);
        if (cargando()) continue;
        int ped = ped_jugador();
        if (!mapa_listo) {
            pedir_ytd("bcnradar_mapa");
            mapa_listo = ytd_listo("bcnradar_mapa");
            if (mapa_listo && !avisado) { apuntar("plano cargado"); avisado = 1; }
        }
        int m = (GetAsyncKeyState('M') & 0x8000) != 0;
        int pulsada = m && !tecla_m_antes;
        tecla_m_antes = m;
        int libre = !menu_pausa() && !pantalla_negra() && !en_escena();
        if (pulsada && libre) {
            mapa_abierto = !mapa_abierto;
            if (mapa_abierto) { float pz; coords(ped, &mx, &my, &pz); mzoom = 3000.0f; }
            GetAsyncKeyState(VK_RETURN);  /* olvida Intro pulsado antes */
        }
        if (mapa_abierto && (GetAsyncKeyState(VK_BACK) & 0x8000)) mapa_abierto = 0;
        if (!libre) mapa_abierto = 0;
        if (automatico && mapa_listo) {
            if (!t_listo) t_listo = GetTickCount();
            DWORD t = GetTickCount() - t_listo;
            static const DWORD MOMENTOS[] = {12000, 16000, 18000, 22000, 24000};
            if (paso < 5 && t > MOMENTOS[paso]) {
                float pz;
                switch (paso) {
                case 0: mapa_abierto = 1; coords(ped, &mx, &my, &pz); mzoom = 14000.0f; break;
                case 2: mzoom = 1200.0f; break;
                case 4: mapa_abierto = 0; break;
                default: keybd_event(VK_F12, 0, 0, 0); Sleep(80); keybd_event(VK_F12, 0, KEYEVENTF_KEYUP, 0);
                         apuntar("captura del mapa");
                }
                paso++;
            }
        }
        mostrar_radar(0);
        if (mapa_abierto) dibujar_mapa(ped);
        else if (libre && !hud_oculto()) { dibujar_radar(ped); dibujar_calle(ped); }
        if (GetTickCount() - ultimo_soltar > 5000) { soltar_viejos(); ultimo_soltar = GetTickCount(); }
    }
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD motivo, LPVOID reservado)
{
    (void)reservado;
    if (motivo == DLL_PROCESS_ATTACH) {
        HMODULE shv = LoadLibraryA("ScriptHookV.dll");
        if (!shv) return FALSE;
        sh_init = (void *)GetProcAddress(shv, "?nativeInit@@YAX_K@Z");
        sh_push = (void *)GetProcAddress(shv, "?nativePush64@@YAX_K@Z");
        sh_call = (void *)GetProcAddress(shv, "?nativeCall@@YAPEA_KXZ");
        sh_wait = (void *)GetProcAddress(shv, "?scriptWait@@YAXK@Z");
        sh_register = (void *)GetProcAddress(shv, "?scriptRegister@@YAXPEAUHINSTANCE__@@P6AXXZ@Z");
        sh_unregister = (void *)GetProcAddress(shv, "?scriptUnregister@@YAXPEAUHINSTANCE__@@@Z");
        if (!sh_init || !sh_push || !sh_call || !sh_wait || !sh_register) return FALSE;
        registro = fopen("bcn_radar.log", "w");
        FILE *f = fopen("bcn_radar_uv.txt", "r");   /* para probar otro hash de la función con UV */
        if (f) { unsigned long long hsh; if (fscanf(f, "%llx", &hsh) == 1) HASH_UV = hsh; fclose(f); }
        sh_register(inst, principal);
    } else if (motivo == DLL_PROCESS_DETACH) {
        if (sh_unregister) sh_unregister(inst);
        if (registro) fclose(registro);
    }
    return TRUE;
}
