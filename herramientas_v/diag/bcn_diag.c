/* Plugin de diagnóstico del mapa de Barcelona para ScriptHookV (bcn_diag.asi).
 *
 *   (siempre)  activa nuestros ymap y los vuelve a activar si se apagan: el juego los deja desactivados
 *              aunque estén en el DLC, y al cargar la partida apaga los que se activaron antes
 *   F5  te deja a 300 m sobre Sant Roc (C-31) quieto 8 s, con paracaídas, y mira si el suelo tiene colisión
 *   F8  recorre con una cámara los objetos de prueba, uno cada 6 s y con su nombre en pantalla
 *   F6  comprueba nuestros modelos (y uno del juego) y los crea delante del jugador
 *   F7  pide al juego que cargue nuestros ymap y dice si quedan activos
 *   (si existe bcn_auto.txt en la carpeta del juego)  hace F6 y F8 solo, con una captura de Steam (F12) en
 *        cada vista, y cierra el juego: para probar sin nadie delante
 *
 * Cada resultado sale en pantalla y en bcn_diag.log (carpeta del juego).
 * No enlaza con ScriptHookV.lib (es de MSVC): busca sus funciones exportadas por nombre.
 * Compilar: zig cc -target x86_64-windows-gnu -shared -O2 -o bcn_diag.asi bcn_diag.c
 */
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* Coordenadas del juego del mapa de prueba (BCN_DESPLAZAMIENTO=-7900,-4200) */
#define SANTROC_X (-5658.0f)  /* BCN_DESPLAZAMIENTO="-10400,-4200" */
#define SANTROC_Y (-1822.0f)

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

/* Sólo se consultan (los carga el paquete de nivel solo): LOD y HD de Llefià y de Sant Roc */
static const char *YMAPS[] = {"bcn_434589_lod", "bcn_434589", "bcn_435587_lod", "bcn_435587"};
#define N_YMAPS 4

static int jugador(void) { sh_init(0xD80958FC74E988A6ULL); return (int)*llamar(); }
static uint32_t hash(const char *s) { sh_init(0xD24D37CC275948CCULL); pp(s); return (uint32_t)*llamar(); }
static void posicion(int ent, float *x, float *y, float *z)
{
    sh_init(0x3FEF770D40960D5AULL); pi(ent); pi(1);
    float *v = (float *)llamar();  /* Vector3 del juego: x, relleno, y, relleno, z, relleno */
    *x = v[0]; *y = v[2]; *z = v[4];
}
static void mover(int ent, float x, float y, float z)
{
    sh_init(0x06843DA7060A026BULL); pi(ent); pf(x); pf(y); pf(z); pi(0); pi(0); pi(0); pi(1); llamar();
}
static int b1(uint64_t h, uint32_t a) { sh_init(h); pi(a); return (int)(*llamar() & 1); }
static int en_imagen(uint32_t m) { return b1(0x35B9E0803292B641ULL, m); }
static int valido(uint32_t m) { return b1(0xC0296A2EDF545E92ULL, m); }
static int cargado(uint32_t m) { return b1(0x98A4EB5D89A0C952ULL, m); }
static void pedir_modelo(uint32_t m) { sh_init(0x963D27A58DF860ACULL); pi(m); llamar(); }
static int crear(uint32_t m, float x, float y, float z)
{
    sh_init(0x509D5878EB39E842ULL); pi(m); pf(x); pf(y); pf(z); pi(0); pi(1); pi(0); return (int)*llamar();
}
static void pedir_ipl(const char *n) { sh_init(0x41B4893843BBDB74ULL); pp(n); llamar(); }
static void quitar_ipl(const char *n) { sh_init(0xEE6C5AD3ECE0A82DULL); pp(n); llamar(); }
static int cargando(void) { sh_init(0x10D0A8F259E93EC9ULL); return (int)(*llamar() & 1); }
static void avisar(const char *texto);
static int ipl_activo(const char *n) { sh_init(0x88A741E44A2B3495ULL); pp(n); return (int)(*llamar() & 1); }
static void estado_ymaps(const char *cuando)
{
    char t[256];
    snprintf(t, sizeof t, "ymaps activos %s: %s=%d %s=%d %s=%d %s=%d", cuando, YMAPS[0], ipl_activo(YMAPS[0]),
             YMAPS[1], ipl_activo(YMAPS[1]), YMAPS[2], ipl_activo(YMAPS[2]), YMAPS[3], ipl_activo(YMAPS[3]));
    avisar(t);
}
static void congelar(int ent, int si) { sh_init(0x428CA6DBD1094446ULL); pi(ent); pi(si); llamar(); }
static void pedir_colision(float x, float y, float z) { sh_init(0x07503F7948F491A7ULL); pf(x); pf(y); pf(z); llamar(); }
static void paracaidas(int ped) { sh_init(0xBF0FD6E56C964FCBULL); pi(ped); pi(0xFBAB5776); pi(1); pi(0); pi(1); llamar(); }
static int suelo(float x, float y, float *z)
{
    sh_init(0xC906A7DAB05C8D2BULL); pf(x); pf(y); pf(1000.0f); pp(z); pi(0); return (int)(*llamar() & 1);
}
static int camara(float x, float y, float z, float cabeceo, float rumbo)
{
    sh_init(0xB51194800B257161ULL); pp("DEFAULT_SCRIPTED_CAMERA"); pf(x); pf(y); pf(z); pf(cabeceo); pf(0.0f); pf(rumbo);
    pf(60.0f); pi(1); pi(2); return (int)*llamar();
}
static void ver_camaras(int si) { sh_init(0x07E5B515DB0636FCULL); pi(si); pi(0); pi(0); pi(1); pi(0); pi(0); llamar(); }
static void destruir_camara(int c) { sh_init(0x865908C81A2C22E9ULL); pi(c); pi(0); llamar(); }
static void foco(float x, float y, float z) { sh_init(0xBB7454BAFF08FE25ULL); pf(x); pf(y); pf(z); pf(0); pf(0); pf(0); llamar(); }
static void sin_foco(void) { sh_init(0x31B73D1EA9F01DA2ULL); llamar(); }
static void pedir_ytd(const char *n) { sh_init(0xDFA2EF8E04127DD5ULL); pp(n); pi(0); llamar(); }
static int ytd_cargado(const char *n) { sh_init(0x0145F696AAAAD2E4ULL); pp(n); return (int)(*llamar() & 1); }
static int automatico;
static void captura(void);
static int en_agua(int ent) { sh_init(0xCFB0A0D8EDD145A3ULL); pi(ent); return (int)(*llamar() & 1); }

/* Pone al jugador de pie en varios puntos de Sant Roc, justo encima del suelo que da la colisión: si no hay
 * colisión, no encuentra suelo y acaba en el mar (en_agua=1) */
static void probar_colision(void)
{
    static const float PUNTOS[][2] = {{SANTROC_X + 60.0f, SANTROC_Y}, {SANTROC_X - 150.0f, SANTROC_Y + 100.0f},
                                      {SANTROC_X + 200.0f, SANTROC_Y - 150.0f},
                                      {-5680.8f, -532.7f}};  /* 4: tejado de un bloque de Progrés (91,6 m; suelo ~67) */
    char t[256];
    int ped = jugador();
    for (int k = 0; k < 4; k++) {
        float x = PUNTOS[k][0], y = PUNTOS[k][1], z = 0.0f;
        congelar(ped, 1);
        mover(ped, x, y, 130.0f);
        int hay = 0;
        for (int i = 0; i < 50 && !(hay = suelo(x, y, &z)); i++) { pedir_colision(x, y, 10.0f); sh_wait(100); }
        if (hay) mover(ped, x, y, z + 1.0f);
        congelar(ped, 0);
        sh_wait(5000);
        posicion(ped, &x, &y, &z);
        snprintf(t, sizeof t, "Colision punto %d: suelo=%d z=%.1f en_agua=%d", k + 1, hay, z, en_agua(ped));
        avisar(t);
        if (automatico) captura();
        sh_wait(1000);
    }
}

static void captura(void)
{
    keybd_event(VK_F12, 0, 0, 0); Sleep(80); keybd_event(VK_F12, 0, KEYEVENTF_KEYUP, 0);
}
static void hora(int h) { sh_init(0x47C3B5848C3E45D8ULL); pi(h); pi(0); pi(0); llamar(); }

static void avisar(const char *texto)
{
    static char copia[256];
    strncpy(copia, texto, sizeof copia - 1);
    sh_init(0x202709F4C58A0424ULL); pp("STRING"); llamar();
    sh_init(0x6C188BE134E074AAULL); pp(copia); llamar();
    sh_init(0x2ED7843F8F801023ULL); pi(0); pi(1); llamar();
    if (registro) { fprintf(registro, "%s\n", texto); fflush(registro); }
}

static const char *MODELOS[] = {"prop_streetlight_01", "prop_streetlight_01b", "prop_streetlight_03", "prop_streetlight_03b", "prop_streetlight_05", "prop_streetlight_09", "prop_streetlight_11a", "prop_traffic_01a", "prop_traffic_01b", "prop_traffic_01d", "prop_traffic_02a", "prop_traffic_03a", "prop_bench_01a", "prop_bench_02", "prop_bench_05", "prop_bench_07", "prop_bin_01a", "prop_bin_05a", "prop_bin_07a", "prop_dumpster_01a", "prop_dumpster_02a", "prop_recyclebin_01a", "prop_recyclebin_04a", "prop_busstop_02", "prop_busstop_04", "prop_busstop_05", "prop_bus_stop_sign", "prop_fire_hydrant_1", "prop_postbox_01a", "prop_parknmeter_01", "prop_bollard_02a", "prop_bollard_04", "prop_tree_birch_01", "prop_tree_birch_02", "prop_tree_birch_03", "prop_tree_birch_04", "prop_tree_oak_01", "prop_tree_olive_01", "prop_tree_jacada_01", "prop_tree_jacada_02", "prop_tree_cedar_02", "prop_tree_cedar_03", "prop_tree_pine_01", "prop_tree_pine_02", "prop_tree_eucalip_01", "prop_tree_maple_02", "prop_tree_maple_03", "prop_palm_med_01a", "prop_palm_med_01b", "prop_palm_sm_01a", "prop_palm_fan_03_a", "prop_palm_huge_01a", "prop_bush_med_03", "prop_plant_int_01a", "test_tree_forest_trunk_01", "prop_tree_lficus_02", "prop_tree_lficus_03", "prop_tree_mquite_01", "prop_tree_stump_01", "prop_sign_road_01a", "prop_sign_road_03a", "prop_elecbox_01a", "prop_telegraph_01a", "prop_phonebox_01a", "prop_news_disp_01a", "prop_bikerack_1a", "prop_fountain2", "prop_parasol_04"};
#define N_MODELOS 68

static void comprobar_modelos(void)
{
    /* qué props del juego existen (para árboles y mobiliario urbano): solo se consulta, no se crea nada */
    char t[256];
    for (int k = 0; k < N_MODELOS; k++) {
        uint32_t m = hash(MODELOS[k]);
        snprintf(t, sizeof t, "PROP %s en_imagen=%d valido=%d", MODELOS[k], en_imagen(m), valido(m));
        if (registro) { fprintf(registro, "%s\n", t); fflush(registro); }  /* solo al registro, no en pantalla */
    }
}

/* bcn_modelos.txt (si está): un nombre de modelo por línea; apunta en el registro si el juego lo conoce
 * (para saber qué paquetes DLC se han montado) */
static void comprobar_lista(void)
{
    char n[128], t[256];
    FILE *f = fopen("bcn_modelos.txt", "r");
    if (!f) return;
    while (fscanf(f, "%127s", n) == 1) {
        if (!strncmp(n, "dlc:", 4)) {  /* "dlc:<nameHash>": IS_DLC_PRESENT (¿el juego ha registrado el paquete?) */
            sh_init(0x812595A0644CE1DEULL); pi(hash(n + 4));
            snprintf(t, sizeof t, "DLC %s presente=%d", n + 4, (int)(*llamar() & 1));
            if (registro) { fprintf(registro, "%s\n", t); fflush(registro); }
            continue;
        }
        uint32_t m = hash(n);
        snprintf(t, sizeof t, "MODELO %s en_imagen=%d valido=%d", n, en_imagen(m), valido(m));
        if (registro) { fprintf(registro, "%s\n", t); fflush(registro); }
    }
    fclose(f);
}

static void comprobar_ymaps(void)
{
    char t[256];
    for (int k = 0; k < N_YMAPS; k++) {
        int antes = ipl_activo(YMAPS[k]);
        pedir_ipl(YMAPS[k]);
        sh_wait(500);
        snprintf(t, sizeof t, "ymap %s: activo antes=%d despues=%d", YMAPS[k], antes, ipl_activo(YMAPS[k]));
        avisar(t);
    }
}

static void ir_a_santroc(void)
{
    char t[256];
    int ped = jugador();
    float z = 0.0f;
    hora(12);
    paracaidas(ped);
    congelar(ped, 1);
    mover(ped, SANTROC_X, SANTROC_Y, 300.0f);
    for (int i = 0; i < 80; i++) { pedir_colision(SANTROC_X, SANTROC_Y, 20.0f); sh_wait(100); }
    int hay = suelo(SANTROC_X, SANTROC_Y, &z);
    snprintf(t, sizeof t, "Sant Roc: suelo con colision=%d z=%.1f (ymap activo=%d). Abre el paracaidas!", hay, z,
             ipl_activo("bcn_435587"));
    avisar(t);
    congelar(ped, 0);
}

/* Objetos de prueba de bcn_balizas (empaquetar_v.balizas): base de la torre 1 en (-4870, -1170) */
#define BX (-4870.0f)
#define BY (-1170.0f)
static const struct { const char *nombre; float x, y, z, cabeceo, rumbo; } VISTAS[] = {
    {"6 Sant Roc desde el aire (sur)", SANTROC_X, SANTROC_Y - 500.0f, 220.0f, -25.0f},
    {"7 Sant Roc y la C-31 de cerca", SANTROC_X, SANTROC_Y - 180.0f, 70.0f, -15.0f},
    {"8 C-31 a la altura de la calle", SANTROC_X, SANTROC_Y - 60.0f, 22.0f, 0.0f},
    {"9 Llefia desde el aire (sur)", -6900.0f, -420.0f, 300.0f, -25.0f},
    {"10 Sant Adria (hojas 434586 y 435586)", -6400.0f, -3350.0f, 260.0f, -25.0f},
    {"11 Badalona centro (436588 y 436589)", -5400.0f, -1000.0f, 320.0f, -25.0f},
    {"12 Vista general de las hojas", -6000.0f, -4300.0f, 750.0f, -30.0f},
    {"13 Tres Xemeneies desde el suroeste", -5120.0f, -3100.0f, 30.0f, 12.0f, -42.0f},
    {"14 Tres Xemeneies desde la playa", -4550.0f, -2950.0f, 8.0f, 24.0f, 56.0f},
    {"15 Pont del Petroli y Anis del Mono desde el mar", -3450.0f, -1550.0f, 35.0f, -6.0f, 40.0f},
    {"16 Bola del Magic desde el suroeste", -5320.0f, -990.0f, 42.0f, -6.0f, -45.0f},
    {"17 Calle y aparcamiento bajo la C-31 (Sant Roc)", -5680.0f, -1895.0f, 6.5f, 4.0f, -35.0f},
    {"18 Viaducto C-31 a lo largo (continuidad)", -6000.0f, -2560.0f, 30.0f, -6.0f, -28.0f},
    {"19 Arboles y farolas en Sant Roc (a pie de calle)", SANTROC_X - 40.0f, SANTROC_Y - 40.0f, 9.0f, -4.0f, -35.0f},
    {"20 Av. d'en Caritg bajo la C-31, junto al Magic", -5290.0f, -978.0f, 10.0f, 0.0f, -126.0f},
    {"21 Viaducto C-31 sobre el Gorg desde arriba", -5230.0f, -1120.0f, 24.0f, -8.0f, -145.0f},
};
#define N_VISTAS 16

static void ir_a_pruebas(void)
{
    char t[256];
    int ped = jugador();
    hora(12);
    sh_init(0x3882114BDE571AD4ULL); pi(ped); pi(1); llamar();  /* SET_ENTITY_INVINCIBLE: que no muera al moverlo */
    congelar(ped, 1);
    mover(ped, SANTROC_X, SANTROC_Y - 300.0f, 120.0f);
    pedir_ytd("bcn_obra");
    for (int i = 0; i < 100 && !ytd_cargado("bcn_obra"); i++) sh_wait(30);
    snprintf(t, sizeof t, "Texturas bcn_obra cargadas=%d. Haz una captura (F12) en cada vista", ytd_cargado("bcn_obra"));
    avisar(t);
    /* bcn_vistas.txt (si está): una vista por línea "x y z cabeceo rumbo nombre", en lugar de las de VISTAS */
    static struct { char nombre[96]; float x, y, z, cabeceo, rumbo; } lista[200];
    int n = 0;
    FILE *fv = fopen("bcn_vistas.txt", "r");
    if (fv) {
        char linea[256];
        while (n < 200 && fgets(linea, sizeof linea, fv)) {
            int usados = 0;
            if (sscanf(linea, "%f %f %f %f %f %n", &lista[n].x, &lista[n].y, &lista[n].z, &lista[n].cabeceo,
                       &lista[n].rumbo, &usados) >= 5) {
                snprintf(lista[n].nombre, sizeof lista[n].nombre, "%s", linea + usados);
                lista[n].nombre[strcspn(lista[n].nombre, "\r\n")] = 0;
                n++;
            }
        }
        fclose(fv);
    } else {
        for (; n < N_VISTAS; n++) {
            snprintf(lista[n].nombre, sizeof lista[n].nombre, "%s", VISTAS[n].nombre);
            lista[n].x = VISTAS[n].x; lista[n].y = VISTAS[n].y; lista[n].z = VISTAS[n].z;
            lista[n].cabeceo = VISTAS[n].cabeceo; lista[n].rumbo = VISTAS[n].rumbo;
        }
    }
    for (int k = 0; k < n; k++) {
        foco(lista[k].x, lista[k].y, 0.0f);
        mover(ped, lista[k].x, lista[k].y, lista[k].z + 40.0f);  /* el jugador cerca: carga lo de alrededor */
        int c = camara(lista[k].x, lista[k].y, lista[k].z, lista[k].cabeceo, lista[k].rumbo);  /* rumbo 0 = norte, + = oeste */
        ver_camaras(1);
        snprintf(t, sizeof t, "Vista %s: deberia estar en el centro", lista[k].nombre);
        avisar(t);
        sh_wait(9000);  /* las hojas tardan en cargar */
        if (automatico) { captura(); avisar("captura"); }
        if (k == 3) estado_ymaps("en Llefia");
        sh_wait(2000);
        ver_camaras(0);
        destruir_camara(c);
    }
    sin_foco();
    congelar(ped, 0);
    avisar("Fin de las vistas");
}

static void principal(void)
{
    int antes[4] = {0, 0, 0, 0};
    const int teclas[4] = {VK_F5, VK_F6, VK_F7, VK_F8};
    while (cargando()) sh_wait(500);
    sh_wait(8000);  /* que termine de cargar la partida, que apaga los ymap pedidos antes */
    char t[128];
    avisar("bcn_diag listo: F5 Sant Roc, F6 modelos, F7 ymaps, F8 pruebas, F9 marcar fallo");
    estado_ymaps("al empezar");
    FILE *f = fopen("bcn_auto.txt", "r");
    if (f) {
        fclose(f);
        automatico = 1;
        FILE *fv = fopen("bcn_vistas.txt", "r");  /* con vistas propias, solo las vistas */
        if (fv) fclose(fv);
        if (!fv) comprobar_modelos();
        comprobar_lista();
        ir_a_pruebas();
        if (!fv) probar_colision();
        avisar("AUTO FIN");
        sh_wait(3000);
        if (registro) fclose(registro);
        TerminateProcess(GetCurrentProcess(), 0);
    }

    int antes_f9 = 0;
    FILE *rastro = fopen("bcn_rastro.txt", "w");  /* posición cada segundo: si el juego se cierra, dónde fue */
    DWORD ultimo = 0;
    for (;;) {
        if (rastro && GetTickCount() - ultimo >= 1000) {
            float x, y, z;
            posicion(jugador(), &x, &y, &z);
            SYSTEMTIME ahora;
            GetLocalTime(&ahora);
            fprintf(rastro, "%02d:%02d:%02d %.1f %.1f %.1f\n", ahora.wHour, ahora.wMinute, ahora.wSecond, x, y, z);
            fflush(rastro);
            ultimo = GetTickCount();
        }
        int f9 = (GetAsyncKeyState(VK_F9) & 0x8000) != 0;
        static int marcas;
        if (f9 && !antes_f9) {  /* F9: apunta dónde está el jugador (para avisar de fallos del mapa) */
            float x, y, z;
            posicion(jugador(), &x, &y, &z);
            SYSTEMTIME ahora;
            GetLocalTime(&ahora);
            FILE *m = fopen("bcn_marcas.txt", "a");  /* aparte del registro: probar.sh lo vacía */
            if (m) {
                /* y la cámara (posición, cabeceo y rumbo): con eso se repite la vista exacta (bcn_vistas.txt) */
                sh_init(0x14D6F5678D8F1B37ULL);  /* GET_GAMEPLAY_CAM_COORD */
                float *c = (float *)llamar();
                float cx = c[0], cy = c[2], cz = c[4];
                sh_init(0x837765A25378F0BBULL); pi(2);  /* GET_GAMEPLAY_CAM_ROT */
                float *r = (float *)llamar();
                fprintf(m, "%02d:%02d:%02d %.1f %.1f %.1f cam %.1f %.1f %.1f %.1f %.1f\n", ahora.wHour, ahora.wMinute,
                        ahora.wSecond, x, y, z, cx, cy, cz, r[0], r[4]);
                fclose(m);
            }
            char t[128];
            snprintf(t, sizeof t, "Marca %d guardada: %.0f %.0f %.0f", ++marcas, x, y, z);
            avisar(t);
        }
        antes_f9 = f9;
        for (int k = 0; k < 4; k++) {
            int ahora = (GetAsyncKeyState(teclas[k]) & 0x8000) != 0;
            if (ahora && !antes[k]) {
                if (k == 0) {
                    ir_a_santroc();
                } else if (k == 1) {
                    comprobar_modelos();
                } else if (k == 2) {
                    comprobar_ymaps();
                } else {
                    ir_a_pruebas();
                }
            }
            antes[k] = ahora;
        }
        sh_wait(0);
    }
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD motivo, LPVOID reservado)
{
    (void)reservado;
    if (motivo == DLL_PROCESS_ATTACH) {
        HMODULE shv = LoadLibraryA("ScriptHookV.dll");  /* el cargador de .asi puede ir antes que ScriptHookV */
        if (!shv) return FALSE;
        sh_init = (void *)GetProcAddress(shv, "?nativeInit@@YAX_K@Z");
        sh_push = (void *)GetProcAddress(shv, "?nativePush64@@YAX_K@Z");
        sh_call = (void *)GetProcAddress(shv, "?nativeCall@@YAPEA_KXZ");
        sh_wait = (void *)GetProcAddress(shv, "?scriptWait@@YAXK@Z");
        sh_register = (void *)GetProcAddress(shv, "?scriptRegister@@YAXPEAUHINSTANCE__@@P6AXXZ@Z");
        sh_unregister = (void *)GetProcAddress(shv, "?scriptUnregister@@YAXPEAUHINSTANCE__@@@Z");
        if (!sh_init || !sh_push || !sh_call || !sh_wait || !sh_register) return FALSE;
        registro = fopen("bcn_diag.log", "a");
        sh_register(inst, principal);
    } else if (motivo == DLL_PROCESS_DETACH) {
        if (sh_unregister) sh_unregister(inst);
        if (registro) fclose(registro);
    }
    return TRUE;
}
