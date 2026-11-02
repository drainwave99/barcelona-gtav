/* Modo libre (sandbox) para el mapa de Barcelona, plugin de ScriptHookV (bcn_sandbox.asi).
 *
 * Sin Los Santos el modo historia no tiene sentido (misiones, llamadas, hospitales y comisarías estarían en el
 * mar o dentro de edificios de Barcelona), así que:
 *   - al cargar la partida y cada pocos segundos para los scripts de la historia (flujo de misiones, quien las
 *     lanza, personajes, familia, llamadas y correos, coches aparcados de la historia...) si están corriendo;
 *   - al empezar te pone de pie en Barcelona (Sant Roc), porque la partida guardada te dejaría en Los Santos;
 *   - al morir o ser detenido, cuando el juego te «resucita» en su hospital o comisaría, te devuelve a Barcelona.
 *   - apaga los IPL del juego (bcn_ipl_fuera.txt, lo escribe quitar_ls.py) que los scripts activan por nombre y
 *     que, sin el mapa debajo, quedarían flotando sobre el mar;
 * Lo que hace queda en bcn_sandbox.log (carpeta del juego). Quitarlo: borrar bcn_sandbox.asi.
 *
 * No enlaza con ScriptHookV.lib (es de MSVC): busca sus funciones exportadas por nombre.
 * Compilar: zig cc -target x86_64-windows-gnu -shared -O2 -o bcn_sandbox.asi bcn_sandbox.c
 */
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

/* Punto de salida en coordenadas del juego (mapa en su sitio, sin desplazamiento): Sant Roc (C-31) */
#define SALIDA_X 4742.0f
#define SALIDA_Y 2378.0f
static float salida_x = SALIDA_X, salida_y = SALIDA_Y;  /* bcn_salida.txt ("x y") lo cambia */

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

static int ped_jugador(void) { sh_init(0xD80958FC74E988A6ULL); return (int)*llamar(); }
static int id_jugador(void) { sh_init(0x4F8644AF03D0E0D6ULL); return (int)*llamar(); }
static uint32_t hash(const char *s) { sh_init(0xD24D37CC275948CCULL); pp(s); return (uint32_t)*llamar(); }
static int cargando(void) { sh_init(0x10D0A8F259E93EC9ULL); return (int)(*llamar() & 1); }
static int muerto(int ent) { sh_init(0x5F9532F3B5CC2551ULL); pi(ent); pi(0); return (int)(*llamar() & 1); }
static int detenido(int jug) { sh_init(0x388A47C51ABDAC8EULL); pi(jug); pi(1); return (int)(*llamar() & 1); }
static int pantalla_negra(void) { sh_init(0xB16FCE9DDC7BA182ULL); return (int)(*llamar() & 1); }
static void aclarar(int ms) { sh_init(0xD4E8E24955024033ULL); pi(ms); llamar(); }
static int corriendo(const char *s)
{
    sh_init(0x2C83A9DA6BFFC4F9ULL); pi(hash(s)); return (int)*llamar();  /* hilos con ese script */
}
static void parar(const char *s) { sh_init(0x9DC711BC69C548DFULL); pp(s); llamar(); }
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
static void sin_busqueda(int jug) { sh_init(0x39FF19C64EF7DA5BULL); pi(jug); pi(0); pi(0); llamar(); }
static void aplicar_busqueda(int jug) { sh_init(0xE0A7D1E497FFCD6FULL); pi(jug); pi(0); llamar(); }

static int ipl_activo(const char *n) { sh_init(0x88A741E44A2B3495ULL); pp(n); return (int)(*llamar() & 1); }
static void quitar_ipl(const char *n) { sh_init(0xEE6C5AD3ECE0A82DULL); pp(n); llamar(); }

static char *ipl_texto;     /* bcn_ipl_fuera.txt entero, con un 0 al final de cada nombre */
static char **ipl;
static int n_ipl;

static void cargar_ipl(void)
{
    FILE *f = fopen("bcn_ipl_fuera.txt", "rb");
    if (!f) return;
    fseek(f, 0, SEEK_END);
    long t = ftell(f);
    fseek(f, 0, SEEK_SET);
    ipl_texto = malloc(t + 1);
    if (!ipl_texto || fread(ipl_texto, 1, t, f) != (size_t)t) { fclose(f); return; }
    fclose(f);
    ipl_texto[t] = 0;
    int lineas = 1;
    for (long i = 0; i < t; i++) lineas += ipl_texto[i] == '\n';
    ipl = malloc(sizeof(char *) * lineas);
    char *p = ipl_texto;
    while (*p) {
        char *fin = p + strcspn(p, "\r\n");
        int hay_mas = *fin != 0;
        *fin = 0;
        /* nunca los nuestros (bcn_, bcn2_, bcn3_...): apagarlos deja el paquete entero sin dibujar */
        int nuestro = !strncmp(p, "bcn", 3) && (p[3 + strspn(p + 3, "0123456789")] == '_');
        if (*p && !nuestro) ipl[n_ipl++] = p;
        p = hay_mas ? fin + 1 : fin;
        while (*p == '\r' || *p == '\n') p++;
    }
}

static void apuntar(const char *texto);

/* Una pasada por la lista, de 400 en 400 por fotograma para no dar tirones */
static void apagar_ipl(void)
{
    int n = 0;
    for (int i = 0; i < n_ipl; i++) {
        if (ipl_activo(ipl[i])) { quitar_ipl(ipl[i]); n++; }
        if (i % 400 == 399) sh_wait(0);
    }
    if (n) {
        char t[96];
        snprintf(t, sizeof t, "IPL del juego apagados: %d (de %d)", n, n_ipl);
        apuntar(t);
    }
}

static void apuntar(const char *texto)
{
    if (!registro) return;
    SYSTEMTIME t;
    GetLocalTime(&t);
    fprintf(registro, "%02d:%02d:%02d %s\n", t.wHour, t.wMinute, t.wSecond, texto);
    fflush(registro);
}

/* Scripts del modo historia. Los del jugador, el móvil, la policía, las tiendas, la radio y el respawn (el
 * juego lo necesita para resucitarte) se quedan. */
static const char *HISTORIA[] = {
    "flow_controller", "flow_autoplay", "flowstartaccept", "mission_triggerer_a", "mission_triggerer_b",
    "mission_triggerer_c", "mission_triggerer_d", "mission_stat_watcher", "mission_repeat_controller",
    "randomchar_controller", "friends_controller", "friends_debug_controller", "family_scene_m",
    "family_scene_f0", "family_scene_f1", "family_scene_t0", "family_scene_t1", "family_controller",
    "comms_controller", "email_controller", "bootycallhandler", "blip_controller", "building_controller",
    "vehicle_gen_controller", "code_controller", "stock_controller", "event_controller",
    "context_controller", "shop_robberies", "taxiservice", "taxilauncher", "ambient_tonya", "ambient_tonyacall",
    "ambient_tonyacall2", "ambient_tonyacall5", "ambient_ufos", "forsalesigns", "lesterhandler",
    "michael_events", "chop", "chop_controller", "ambient_mrsphilips", "beach_exterior", "bailbond_launcher",
    "dynamixtest", "launcher_abigail", "launcher_barry", "launcher_basejumpheli", "launcher_basejumppack",
    "launcher_carwash", "launcher_darts", "launcher_dreyfuss", "launcher_epsilon", "launcher_extreme",
    "launcher_fanatic", "launcher_golf", "launcher_hao", "launcher_hunting", "launcher_hunting_ambient",
    "launcher_josh", "launcher_maude", "launcher_minute", "launcher_mrsphilips", "launcher_nigel",
    "launcher_offroadracing", "launcher_omega", "launcher_paparazzo", "launcher_pilotschool", "launcher_racing",
    "launcher_rampage", "launcher_range", "launcher_stunts", "launcher_tennis", "launcher_thelastone",
    "launcher_tonya", "launcher_triathlon", "launcher_yoga", "re_abandonedcar", "re_accident", "re_armybase",
    "re_arrests", "re_atmrobbery", "re_bikethief", "re_border", "re_burials", "re_bus_tours", "re_cartheft",
    "re_chasethieves", "re_crashrescue", "re_cultshootout", "re_dealgonewrong", "re_domestic", "re_drunkdriver",
    "re_duel", "re_gang_intimidation", "re_gangfight", "re_getaway_driver", "re_hitch_lift", "re_homeland_security",
    "re_lossantosintl", "re_lured", "re_monkey", "re_mountdance", "re_muggings", "re_paparazzi", "re_prison",
    "re_prisonerlift", "re_prisonvanbreak", "re_rescuehostage", "re_seaplane", "re_securityvan", "re_shoprobbery",
    "re_snatched", "re_stag_do", "re_yetarian", "ob_abatdoor", "ob_abattoircut", "ob_airdancer", "ob_bong",
    "ob_cashregister", "ob_drinking_shots", "ob_foundry_cauldron", "ob_franklin_beer", "ob_franklin_tv",
    "ob_franklin_wine", "ob_huffing_gas", "ob_mp_bed_high", "ob_mp_bed_low", "ob_mp_bed_med", "ob_mp_shower_med",
    "ob_mp_stripper", "ob_mr_raspberry_jam", "ob_poledancer", "ob_sofa_franklin", "ob_sofa_michael",
    "ob_telescope", "ob_tv", "ob_vend1", "ob_vend2", "ob_wheatgrass", "savegame_bed", "director_mode",
};
#define N_HISTORIA ((int)(sizeof HISTORIA / sizeof HISTORIA[0]))

static void parar_hilos(int avisar)
{
    static char ya[N_HISTORIA];
    int n = 0;
    sh_init(0xDADFADA5A20143A8ULL); llamar();  /* SCRIPT_THREAD_ITERATOR_RESET */
    for (;;) {
        sh_init(0x30B4FA1C82DD4B9FULL);  /* SCRIPT_THREAD_ITERATOR_GET_NEXT_THREAD_ID */
        int id = (int)*llamar();
        if (!id || n++ > 400) break;
        sh_init(0x05A42BA9FC8DA96BULL); pi(id);  /* GET_NAME_OF_SCRIPT_WITH_THIS_ID */
        const char *nom = (const char *)(uintptr_t)*llamar();
        if (!nom) continue;
        for (int i = 0; i < N_HISTORIA; i++) {
            if (_stricmp(nom, HISTORIA[i])) continue;
            sh_init(0xC8B189ED9138BCD4ULL); pi(id); llamar();  /* TERMINATE_THREAD */
            if (avisar && !ya[i]) {
                ya[i] = 1;
                char t[128];
                snprintf(t, sizeof t, "hilo terminado: %s", nom);
                apuntar(t);
            }
            break;
        }
    }
}

static void parar_historia(int avisar)
{
    parar_hilos(avisar);
    static char ya[N_HISTORIA];  /* al registro solo la primera vez (los re_* vuelven a lanzarse sin parar) */
    for (int i = 0; i < N_HISTORIA; i++) {
        if (corriendo(HISTORIA[i]) > 0) {
            parar(HISTORIA[i]);
            if (avisar && !ya[i]) {
                ya[i] = 1;
                char t[128];
                snprintf(t, sizeof t, "parado: %s", HISTORIA[i]);
                apuntar(t);
            }
        }
    }
}

static void apuntar_scripts(void);

/* Llamadas de la historia que ya estaban en cola en la partida guardada (Simeon): las lleva el propio móvil,
   aunque comms_controller esté parado. Si suena el móvil del jugador, se cuelga (como pulsar Retroceso). */
static void colgar(void)
{
    static int veces;
    int ped = ped_jugador();
    sh_init(0x1E8E5E20937E3137ULL); pi(ped);  /* IS_PED_RINGTONE_PLAYING */
    int suena = (int)(*llamar() & 1);
    sh_init(0x7497D2CE2C30D24CULL);           /* IS_MOBILE_PHONE_CALL_ONGOING */
    int hablando = (int)(*llamar() & 1);
    if (!suena && !hablando) return;
    if (suena) { sh_init(0x6C5AE23EFA885092ULL); pi(ped); llamar(); }  /* STOP_PED_RINGTONE */
    if (hablando) { sh_init(0xD79DEEFB53455EBAULL); pi(0); llamar(); }  /* STOP_SCRIPTED_CONVERSATION */
    for (int k = 0; k < 3; k += 2) {            /* INPUT_CELLPHONE_CANCEL (177) en el siguiente fotograma */
        sh_init(0xE8A25867FBA3B05EULL); pi(k); pi(177); pf(1.0f); llamar();
    }
    if (veces++ < 3) {
        char t[64];
        snprintf(t, sizeof t, "llamada colgada (suena=%d hablando=%d)", suena, hablando);
        apuntar(t);
        if (veces == 1) apuntar_scripts();
    }
}

/* De pie en el punto de salida: congela, espera la colisión y busca el suelo */
static void a_barcelona(const char *por_que)
{
    int ped = ped_jugador();
    float z = 0.0f;
    congelar(ped, 1);
    mover(ped, salida_x, salida_y, 200.0f);
    int hay = 0;
    for (int i = 0; i < 1200 && !(hay = suelo(salida_x, salida_y, &z)); i++) {  /* hasta 2 min: el mapa es grande */
        if (i == 50) mover(ped, salida_x, salida_y, 60.0f);  /* más cerca del suelo, para que cargue antes */
        pedir_colision(salida_x, salida_y, 20.0f);
        parar_hilos(1);
        colgar();
        sh_wait(100);
    }
    mover(ped, salida_x, salida_y, hay ? z + 1.0f : 60.0f);
    congelar(ped, 0);
    sin_busqueda(id_jugador());
    aplicar_busqueda(id_jugador());
    if (pantalla_negra()) aclarar(800);
    char t[160];
    snprintf(t, sizeof t, "a Barcelona (%s): suelo=%d z=%.1f", por_que, hay, z);
    apuntar(t);
}

/* Apunta en el registro los scripts que siguen vivos (para saber cuáles de la historia faltan en la lista) */
static void apuntar_scripts(void)
{
    char t[200];
    int n = 0;
    sh_init(0xDADFADA5A20143A8ULL); llamar();  /* SCRIPT_THREAD_ITERATOR_RESET */
    for (;;) {
        sh_init(0x30B4FA1C82DD4B9FULL);  /* SCRIPT_THREAD_ITERATOR_GET_NEXT_THREAD_ID */
        int id = (int)*llamar();
        if (!id || n++ > 300) break;
        sh_init(0x05A42BA9FC8DA96BULL); pi(id);  /* GET_NAME_OF_SCRIPT_WITH_THIS_ID */
        const char *nom = (const char *)(uintptr_t)*llamar();
        snprintf(t, sizeof t, "vivo: %s", nom ? nom : "?");
        apuntar(t);
    }
}

static void principal(void)
{
    FILE *f = fopen("bcn_salida.txt", "r");
    if (f) {
        if (fscanf(f, "%f %f", &salida_x, &salida_y) != 2) salida_x = SALIDA_X, salida_y = SALIDA_Y;
        fclose(f);
    }
    while (cargando()) sh_wait(500);
    /* desde el primer fotograma: "main" relanza comms_controller y en un fotograma ya hace la llamada pendiente
       (Simeon); antes se esperaban 3 s y luego cada 0,5 s y la llamada se colaba */
    for (DWORD t0 = GetTickCount(); GetTickCount() - t0 < 3000;) { parar_hilos(1); colgar(); sh_wait(0); }
    apuntar("partida cargada");
    parar_historia(1);
    apagar_ipl();
    a_barcelona("inicio");
    DWORD inicio = GetTickCount();
    int listado = 0;
    int estaba_muerto = 0, estaba_detenido = 0;
    DWORD ultimo = GetTickCount();
    for (;;) {
        int ped = ped_jugador(), jug = id_jugador();
        int m = muerto(ped), d = detenido(jug);
        if (m) estaba_muerto = 1;
        if (d) estaba_detenido = 1;
        /* el juego ya te ha resucitado (en su hospital o comisaría): de vuelta a Barcelona */
        if ((estaba_muerto && !m) || (estaba_detenido && !d)) {
            sh_wait(1500);
            a_barcelona(estaba_muerto ? "muerte" : "detencion");
            estaba_muerto = estaba_detenido = 0;
        }
        if (!listado && GetTickCount() - inicio >= 12000) { listado = 1; apuntar_scripts(); }
        colgar();
        parar_hilos(1);  /* en cada fotograma: "main" vuelve a lanzar algunos (comms, triggers...) */
        if (GetTickCount() - ultimo >= 3000) {
            parar_historia(1);
            static int vuelta;
            if (++vuelta % 5 == 0) apagar_ipl();  /* cada 15 s */
            ultimo = GetTickCount();
        }
        sh_wait(0);
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
        registro = fopen("bcn_sandbox.log", "w");
        cargar_ipl();
        sh_register(inst, principal);
    } else if (motivo == DLL_PROCESS_DETACH) {
        if (sh_unregister) sh_unregister(inst);
        if (registro) fclose(registro);
    }
    return TRUE;
}
