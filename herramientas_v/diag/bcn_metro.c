/* Metro de Barcelona, plugin de ScriptHookV (bcn_metro.asi): andén genérico.
 *
 * Lee bcn_metro.txt (de metro_v.py: estaciones, bocas y líneas de OSM) de la carpeta del juego.
 *   - en cada boca, un círculo rojo en el suelo; a pie junto a ella: "E: entrar al metro";
 *   - al entrar: fundido a negro y el panel de líneas y estaciones (flechas: línea y estación; Intro: viajar;
 *     Retroceso: salir otra vez a la calle);
 *   - el viaje: unos segundos en negro, el reloj avanza lo que se tardaría (2 min por parada, 4 por transbordo) y
 *     sales por una boca de la estación de destino;
 *   - las estaciones salen en el mapa del menú de pausa (icono pequeño con su nombre).
 * Compilar: zig cc -target x86_64-windows-gnu -shared -O2 -o bcn_metro.asi bcn_metro.c -luser32
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
static int en_vehiculo(int ped) { sh_init(0x997ABD671D25CA0BULL); pi(ped); pi(0); return (int)(*llamar() & 1); }
static int menu_pausa(void) { sh_init(0xB0034A223497FFCBULL); return (int)(*llamar() & 1); }
static int cargando(void) { sh_init(0x10D0A8F259E93EC9ULL); return (int)(*llamar() & 1); }
static int en_negro(void) { sh_init(0xB16FCE9DDC7BA182ULL); return (int)(*llamar() & 1); }       /* IS_SCREEN_FADED_OUT */
static int en_escena(void) { sh_init(0xD3C2E180A40F031EULL); return (int)(*llamar() & 1); }
static void fundir_negro(int ms) { sh_init(0x891B5B39AC6302AFULL); pi(ms); llamar(); }          /* DO_SCREEN_FADE_OUT */
static void fundir_vuelta(int ms) { sh_init(0xD4E8E24955024033ULL); pi(ms); llamar(); }         /* DO_SCREEN_FADE_IN */
static void sin_controles(void) { sh_init(0x5F4B6931816E599BULL); pi(0); llamar(); }            /* DISABLE_ALL_CONTROL_ACTIONS */
static void quitar_control(int c) { sh_init(0xFE99B66D079CF6BCULL); pi(0); pi(c); pi(1); llamar(); }
static void mover(int ent, float x, float y, float z)
{
    sh_init(0x06843DA7060A026BULL); pi(ent); pf(x); pf(y); pf(z); pi(0); pi(0); pi(0); pi(1); llamar();
}
static void rumbo_poner(int ent, float r) { sh_init(0x8E2530AA8ADA980EULL); pi(ent); pf(r); llamar(); }
static void congelar(int ent, int si) { sh_init(0x428CA6DBD1094446ULL); pi(ent); pi(si); llamar(); }
static void pedir_colision(float x, float y, float z) { sh_init(0x07503F7948F491A7ULL); pf(x); pf(y); pf(z); llamar(); }
static int suelo(float x, float y, float *z)
{
    sh_init(0xC906A7DAB05C8D2BULL); pf(x); pf(y); pf(1000.0f); pp(z); pi(0); return (int)(*llamar() & 1);
}
static void reloj_mas(int minutos) { sh_init(0xD716F30D8C8980E2ULL); pi(0); pi(minutos); pi(0); llamar(); } /* ADD_TO_CLOCK_TIME */
static void rect(float x, float y, float w, float h, int r, int g, int b, int a)
{
    sh_init(0x3A618A217E5154F0ULL); pf(x); pf(y); pf(w); pf(h); pi(r); pi(g); pi(b); pi(a); pi(0); llamar();
}
static void orden(int capa) { sh_init(0x61BB1D9B3A95D802ULL); pi(capa); llamar(); }
static void texto(const char *s, float x, float y, float escala, int centrado, int r, int g, int b)
{
    sh_init(0x66E0276CC5F6B9DAULL); pi(4); llamar();                      /* SET_TEXT_FONT */
    sh_init(0x07C837F9A01C34C9ULL); pf(escala); pf(escala); llamar();   /* SET_TEXT_SCALE */
    sh_init(0xBE6B23FFA53FB442ULL); pi(r); pi(g); pi(b); pi(255); llamar(); /* SET_TEXT_COLOUR */
    sh_init(0x2513DFB0FB8400FEULL); llamar();                            /* SET_TEXT_OUTLINE */
    sh_init(0xC02F4DBFB51D988BULL); pi(centrado); llamar();             /* SET_TEXT_CENTRE */
    sh_init(0x25FBB336DF1804CBULL); pp("STRING"); llamar();             /* BEGIN_TEXT_COMMAND_DISPLAY_TEXT */
    sh_init(0x6C188BE134E074AAULL); pp(s); llamar();
    sh_init(0xCD015E5BB0D96A57ULL); pf(x); pf(y); pi(0); llamar();
}
static void ayuda(const char *s)   /* el recuadro de ayuda de arriba a la izquierda */
{
    sh_init(0x8509B634FBE7DA11ULL); pp("STRING"); llamar();             /* BEGIN_TEXT_COMMAND_DISPLAY_HELP */
    sh_init(0x6C188BE134E074AAULL); pp(s); llamar();
    sh_init(0x238FFE5C7B0498A6ULL); pi(0); pi(0); pi(0); pi(-1); llamar(); /* END_TEXT_COMMAND_DISPLAY_HELP, sin pitido */
}
static void marcador_suelo(float x, float y, float z, int r, int g, int b)   /* DRAW_MARKER: cilindro bajo */
{
    sh_init(0x28477EC23D892089ULL); pi(1); pf(x); pf(y); pf(z - 0.98f); pf(0); pf(0); pf(0); pf(0); pf(0); pf(0);
    pf(1.6f); pf(1.6f); pf(0.6f); pi(r); pi(g); pi(b); pi(110); pi(0); pi(0); pi(2); pi(0); pp(NULL); pp(NULL); pi(0);
    llamar();
}

/* ---- datos (bcn_metro.txt) ---- */
#define MAX_EST 400
#define MAX_BOCAS 1200
#define MAX_LIN 32
#define MAX_PAR 64
typedef struct { char nombre[64]; float x, y; int nb, boca0; } Estacion;
typedef struct { int est; float x, y, z, rumbo; } Boca;
typedef struct { char ref[8]; int r, g, b, n, est[MAX_PAR]; } Linea;
static Estacion est[MAX_EST];
static Boca bocas[MAX_BOCAS];
static Linea lin[MAX_LIN];
static int n_est, n_bocas, n_lin, id_a_est[4096];

static void leer(void)
{
    FILE *f = fopen("bcn_metro.txt", "r");
    if (!f) { apuntar("falta bcn_metro.txt"); return; }
    for (int i = 0; i < 4096; i++) id_a_est[i] = -1;
    char l[512];
    while (fgets(l, sizeof l, f)) {
        l[strcspn(l, "\r\n")] = 0;
        int id, k;
        if (l[0] == 'S' && n_est < MAX_EST) {
            Estacion *e = &est[n_est];
            if (sscanf(l, "S %d %f %f %n", &id, &e->x, &e->y, &k) >= 3 && id >= 0 && id < 4096) {
                snprintf(e->nombre, sizeof e->nombre, "%s", l + k);
                id_a_est[id] = n_est++;
            }
        } else if (l[0] == 'B' && n_bocas < MAX_BOCAS) {
            Boca *b = &bocas[n_bocas];
            if (sscanf(l, "B %d %f %f %f %f", &id, &b->x, &b->y, &b->z, &b->rumbo) == 5 && id >= 0 && id < 4096 &&
                id_a_est[id] >= 0) {
                b->est = id_a_est[id];
                n_bocas++;
            }
        } else if (l[0] == 'L' && n_lin < MAX_LIN) {
            Linea *L = &lin[n_lin];
            char *p = l + 2;
            if (sscanf(p, "%7s %d %d %d %n", L->ref, &L->r, &L->g, &L->b, &k) < 4) continue;
            p += k;
            L->n = 0;
            while (L->n < MAX_PAR && sscanf(p, "%d%n", &id, &k) == 1) {
                p += k;
                if (id >= 0 && id < 4096 && id_a_est[id] >= 0) L->est[L->n++] = id_a_est[id];
            }
            if (L->n >= 2) n_lin++;
        }
    }
    fclose(f);
    for (int i = 0; i < n_est; i++) { est[i].nb = 0; est[i].boca0 = -1; }
    for (int i = 0; i < n_bocas; i++) {
        Estacion *e = &est[bocas[i].est];
        if (e->boca0 < 0) e->boca0 = i;
        e->nb++;
    }
    char t[96];
    snprintf(t, sizeof t, "metro: %d estaciones, %d bocas, %d lineas", n_est, n_bocas, n_lin);
    apuntar(t);
}

static void lineas_de(int e, char *s, size_t n)
{
    s[0] = 0;
    for (int i = 0; i < n_lin; i++)
        for (int j = 0; j < lin[i].n; j++)
            if (lin[i].est[j] == e) {
                size_t k = strlen(s);
                snprintf(s + k, n - k, "%s%s", k ? " " : "", lin[i].ref);
                break;
            }
}

/* paradas y transbordos del viaje más corto (búsqueda en anchura por estaciones; cambiar de línea cuenta) */
static void trayecto(int a, int b, int *paradas, int *transbordos)
{
    static int dist[MAX_EST], via[MAX_EST], cola[MAX_EST];
    for (int i = 0; i < n_est; i++) { dist[i] = -1; via[i] = -1; }
    int ini = 0, fin = 0;
    dist[a] = 0; cola[fin++] = a;
    while (ini < fin) {
        int e = cola[ini++];
        for (int i = 0; i < n_lin; i++)
            for (int j = 0; j < lin[i].n; j++) {
                if (lin[i].est[j] != e) continue;
                for (int d = -1; d <= 1; d += 2) {
                    int k = j + d;
                    if (k < 0 || k >= lin[i].n) continue;
                    int o = lin[i].est[k];
                    if (dist[o] < 0) { dist[o] = dist[e] + 1; via[o] = i; cola[fin++] = o; }
                }
            }
    }
    *paradas = dist[b] < 0 ? 10 : dist[b];
    *transbordos = 0;
    /* aproximado: cuántas líneas distintas se usan por el camino */
    int e = b, ultima = -1;
    while (e != a && e >= 0 && dist[e] > 0) {
        int l = via[e];
        if (ultima >= 0 && l != ultima) (*transbordos)++;
        ultima = l;
        int sig = -1;
        for (int j = 0; j < lin[l].n; j++)
            if (lin[l].est[j] == e) {
                for (int d = -1; d <= 1; d += 2) {
                    int k = j + d;
                    if (k >= 0 && k < lin[l].n && dist[lin[l].est[k]] == dist[e] - 1) sig = lin[l].est[k];
                }
            }
        if (sig < 0) break;
        e = sig;
    }
}

/* ---- viaje ---- */
static const char *cartel;   /* lo que se pinta en negro mientras carga el suelo (el fundido del juego taparía el texto) */
static void sin_hud(void) { sh_init(0x719FF505F097FD20ULL); llamar(); }   /* HIDE_HUD_AND_RADAR_THIS_FRAME */
static void tapar(void)
{
    sin_hud();
    orden(0);
    rect(0.5f, 0.5f, 1.0f, 1.0f, 0, 0, 0, 255);
    orden(1);
    if (cartel) texto(cartel, 0.5f, 0.47f, 0.6f, 1, 255, 255, 255);
}
static void salir_por(int ped, int b)
{
    Boca *bo = &bocas[b];
    float z = bo->z;
    congelar(ped, 1);
    mover(ped, bo->x, bo->y, z + 1.0f);
    int hay = 0;
    for (int i = 0; i < 300; i++) {   /* hasta 15 s: sin suelo cargado se caeria al vacio */
        pedir_colision(bo->x, bo->y, z);
        float zs;
        if (suelo(bo->x, bo->y, &zs) && fabsf(zs - z) < 6.0f) { z = zs; hay = 1; break; }
        for (DWORD t = GetTickCount(); GetTickCount() - t < 50;) { tapar(); sh_wait(0); }
    }
    if (!hay) apuntar("sin suelo en la boca");
    mover(ped, bo->x, bo->y, z + 0.1f);
    rumbo_poner(ped, bo->rumbo);
    congelar(ped, 0);
}

static int tecla(int vk)   /* pulsada ahora (flanco) */
{
    static unsigned char antes[256];
    int ahora = (GetAsyncKeyState(vk) & 0x8000) != 0;
    int r = ahora && !antes[vk];
    antes[vk] = (unsigned char)ahora;
    return r;
}

static void panel(int ped, int origen, int boca_origen)
{
    int l = 0, sel = 0;
    for (int i = 0; i < n_lin; i++)   /* empieza en una línea de la estación */
        for (int j = 0; j < lin[i].n; j++)
            if (lin[i].est[j] == origen) { l = i; sel = j; goto hallada; }
hallada:
    fundir_vuelta(0);   /* el fundido del juego tapa lo que dibuja el script: el panel ya es opaco */
    for (int v = 0; v < 256; v++) tecla(v);   /* olvida lo que estuviera pulsado */
    for (;;) {
        sh_wait(0);
        sin_controles();
        quitar_control(199); quitar_control(200);   /* que el ESC/P no abran el menú de pausa encima */
        if (tecla(VK_LEFT) || tecla('A')) { l = (l + n_lin - 1) % n_lin; if (sel >= lin[l].n) sel = lin[l].n - 1; }
        if (tecla(VK_RIGHT) || tecla('D')) { l = (l + 1) % n_lin; if (sel >= lin[l].n) sel = lin[l].n - 1; }
        if (tecla(VK_UP) || tecla('W')) sel = (sel + lin[l].n - 1) % lin[l].n;
        if (tecla(VK_DOWN) || tecla('S')) sel = (sel + 1) % lin[l].n;
        int salir = tecla(VK_BACK) || tecla(VK_ESCAPE);
        int ir = tecla(VK_RETURN);
        /* dibujo */
        sin_hud();
        orden(0);
        rect(0.5f, 0.5f, 1.0f, 1.0f, 8, 10, 14, 255);
        orden(1);
        texto("METRO", 0.08f, 0.06f, 0.9f, 0, 230, 0, 26);
        char t[160], ls[64];
        lineas_de(origen, ls, sizeof ls);
        snprintf(t, sizeof t, "Estas en %s (%s)", est[origen].nombre, ls);
        texto(t, 0.08f, 0.13f, 0.4f, 0, 220, 220, 220);
        /* líneas: fila de cuadros con su color */
        float ancho = 0.84f / (float)(n_lin > 0 ? n_lin : 1);
        for (int i = 0; i < n_lin; i++) {
            float x = 0.08f + ancho * (i + 0.5f);
            int a = i == l ? 255 : 120;
            rect(x, 0.215f, ancho - 0.004f, i == l ? 0.05f : 0.04f, lin[i].r * a / 255, lin[i].g * a / 255, lin[i].b * a / 255, 255);
            texto(lin[i].ref, x, 0.198f, i == l ? 0.42f : 0.34f, 1, 255, 255, 255);
        }
        /* estaciones de la línea, en columna, con la elegida en el centro */
        Linea *L = &lin[l];
        int filas = 14, primera = sel - filas / 2;
        if (primera > L->n - filas) primera = L->n - filas;
        if (primera < 0) primera = 0;
        for (int k = 0; k < filas && primera + k < L->n; k++) {
            int j = primera + k, e = L->est[j];
            float y = 0.29f + k * 0.043f;
            if (j == sel) rect(0.3f, y + 0.017f, 0.46f, 0.04f, L->r, L->g, L->b, 200);
            rect(0.095f, y + 0.017f, 0.006f, 0.043f, L->r, L->g, L->b, 255);   /* la línea */
            rect(0.095f, y + 0.017f, 0.012f, 0.012f, 255, 255, 255, 255);   /* la parada */
            lineas_de(e, ls, sizeof ls);
            snprintf(t, sizeof t, "%s%s", est[e].nombre, e == origen ? "  (aqui)" : "");
            texto(t, 0.115f, y, 0.42f, 0, 255, 255, 255);
            texto(ls, 0.5f, y + 0.004f, 0.3f, 0, 170, 170, 170);
        }
        int destino = L->est[sel];
        if (destino != origen) {
            int p, tr;
            trayecto(origen, destino, &p, &tr);
            snprintf(t, sizeof t, "A %s: %d paradas%s, unos %d min", est[destino].nombre, p,
                     tr ? (tr == 1 ? ", 1 transbordo" : ", varios transbordos") : "", p * 2 + tr * 4);
            texto(t, 0.6f, 0.4f, 0.42f, 0, 255, 255, 255);
        }
        texto("Izquierda/derecha: linea   Arriba/abajo: estacion   Intro: viajar   Retroceso: salir a la calle",
              0.5f, 0.93f, 0.32f, 1, 200, 200, 200);
        if (salir) {
            cartel = NULL;
            salir_por(ped, boca_origen);
            fundir_negro(0);
            break;
        }
        if (ir && destino != origen) {
            int p, tr;
            trayecto(origen, destino, &p, &tr);
            DWORD t0 = GetTickCount();
            int b = est[destino].boca0 + (int)(GetTickCount() % (DWORD)(est[destino].nb > 0 ? est[destino].nb : 1));
            if (b < 0 || b >= n_bocas || bocas[b].est != destino) b = est[destino].boca0;
            int puesto = 0;
            while (GetTickCount() - t0 < 3500) {   /* el viaje: negro, el nombre y el traqueteo */
                sh_wait(0);
                sin_controles();
                snprintf(t, sizeof t, "Viajando a %s...", est[destino].nombre);
                cartel = t;
                tapar();
                if (!puesto && GetTickCount() - t0 > 300) { salir_por(ped, b); puesto = 1; }
            }
            fundir_negro(0);
            reloj_mas(p * 2 + tr * 4);
            snprintf(t, sizeof t, "viaje %s -> %s: %d paradas, %d transbordos", est[origen].nombre, est[destino].nombre, p, tr);
            apuntar(t);
            break;
        }
    }
    fundir_vuelta(600);
}

/* ---- iconos en el mapa del menú de pausa ---- */
static void poner_iconos(void)
{
    for (int i = 0; i < n_est; i++) {
        sh_init(0x5A039BB0BCA604B6ULL); pf(est[i].x); pf(est[i].y); pf(0.0f); int b = (int)*llamar(); /* ADD_BLIP_FOR_COORD */
        sh_init(0xDF735600A4696DAFULL); pi(b); pi(1); llamar();       /* SET_BLIP_SPRITE: círculo */
        sh_init(0x03D7FB09E75D6B7EULL); pi(b); pi(1); llamar();       /* SET_BLIP_COLOUR: rojo */
        sh_init(0xD38744167B2FA257ULL); pi(b); pf(0.55f); llamar();   /* SET_BLIP_SCALE */
        sh_init(0xBE8BE4FE60E27B72ULL); pi(b); pi(1); llamar();       /* SET_BLIP_AS_SHORT_RANGE */
        sh_init(0x9029B2F3DA924928ULL); pi(b); pi(3); llamar();       /* SET_BLIP_DISPLAY: solo el mapa grande */
        char t[96];
        snprintf(t, sizeof t, "Metro %s", est[i].nombre);
        sh_init(0xF9113A30DE5C6670ULL); pp("STRING"); llamar();       /* BEGIN_TEXT_COMMAND_SET_BLIP_NAME */
        sh_init(0x6C188BE134E074AAULL); pp(t); llamar();
        sh_init(0xBC38B49BCB83BC9BULL); pi(b); llamar();              /* END_TEXT_COMMAND_SET_BLIP_NAME */
    }
}

static void principal(void)
{
    apuntar("bcn_metro en marcha");
    leer();
    int iconos = 0;
    for (;;) {
        sh_wait(0);
        if (cargando() || n_bocas == 0) continue;
        if (!iconos) {
            poner_iconos();
            iconos = 1;
            /* prueba sin nadie delante: bcn_metro_prueba.txt con el nombre de una estación -> a los 20 s, a su boca */
            FILE *fp = fopen("bcn_metro_prueba.txt", "r");
            if (fp) {
                char n[64] = "";
                if (fgets(n, sizeof n, fp)) n[strcspn(n, "\r\n")] = 0;
                fclose(fp);
                for (int i = 0; i < 400; i++) sh_wait(50);
                for (int i = 0; i < n_est; i++)
                    if (!strcmp(est[i].nombre, n) && est[i].boca0 >= 0) {
                        salir_por(ped_jugador(), est[i].boca0);
                        apuntar("prueba: en la boca de la estacion");
                        break;
                    }
            }
        }
        if (menu_pausa() || en_negro() || en_escena()) continue;
        int ped = ped_jugador();
        if (en_vehiculo(ped)) continue;
        float x, y, z;
        coords(ped, &x, &y, &z);
        int cerca = -1;
        float mejor = 2.2f;
        for (int i = 0; i < n_bocas; i++) {
            float dx = bocas[i].x - x, dy = bocas[i].y - y, dz = bocas[i].z - z;
            if (fabsf(dx) > 60 || fabsf(dy) > 60 || fabsf(dz) > 8) continue;
            marcador_suelo(bocas[i].x, bocas[i].y, bocas[i].z + 1.0f, 220, 20, 30);
            float d = sqrtf(dx * dx + dy * dy);
            if (d < mejor && fabsf(dz) < 3.0f) { mejor = d; cerca = i; }
            /* abajo, en el vestibulo al pie de la escalera (bocas_v: de 5 a 17 m de la boca, 4,25 m mas hondo) */
            else if (d < 18.0f && dz > 2.5f && dz < 6.5f && cerca < 0) cerca = i;
        }
        if (cerca < 0) { tecla('E'); continue; }
        char t[160], ls[64];
        lineas_de(bocas[cerca].est, ls, sizeof ls);
        snprintf(t, sizeof t, "Metro %s (%s). Pulsa E para entrar.", est[bocas[cerca].est].nombre, ls);
        ayuda(t);
        quitar_control(51);   /* E: que no haga otra cosa */
        if (tecla('E')) {
            fundir_negro(500);
            for (int i = 0; i < 60 && !en_negro(); i++) sh_wait(20);
            HANDLE marca = CreateMutexA(NULL, FALSE, "Local\\bcn_metro_panel");   /* que bcn_radar.asi no pinte encima */
            panel(ped, bocas[cerca].est, cerca);
            if (marca) CloseHandle(marca);
        }
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
        registro = fopen("bcn_metro.log", "w");
        sh_register(inst, principal);
    } else if (motivo == DLL_PROCESS_DETACH) {
        if (sh_unregister) sh_unregister(inst);
        if (registro) fclose(registro);
    }
    return TRUE;
}
