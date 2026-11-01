// Herramienta de línea de comandos sobre CodeWalker.Core para el mapa de GTA V.
//   cwtool xml <carpeta_xml> <carpeta_salida>   convierte *.ydr.xml, *.ybn.xml, *.ytd.xml, *.ymap.xml,
//                                               *.ytyp.xml (formato XML de CodeWalker/Sollumz) al binario del juego
//   cwtool rpf <carpeta> <archivo.rpf>          empaqueta una carpeta en un RPF sin cifrar (OPEN);
//                                               las subcarpetas que acaban en .rpf se convierten en RPF anidados
//   cwtool dlclist <carpeta_gta> <update.rpf de mods> <pack>
//                                               copia update\update.rpf del juego a la carpeta mods (si no está)
//                                               y añade dlcpacks:/<pack>/ a common\data\dlclist.xml; el original
//                                               no se toca. Las claves salen del GTA5.exe del propio juego.
//   cwtool extraer <carpeta_gta> <carpeta_salida> modelos...
//                                               saca a XML (con sus texturas) los .ydr del juego: para comparar
//                                               con los nuestros y para probar un modelo del juego en nuestro DLC
using System;
using System.Collections.Generic;
using System.Linq;
using System.IO;
using System.Xml;
using CodeWalker.GameFiles;

static class Programa
{
    static int Main(string[] args)
    {
        if (args.Length == 4 && args[0] == "dlclist") return DlcList(args[1], args[2], args[3]);
        if (args.Length >= 4 && args[0] == "abrir") return Abrir(args[1], args[2], args[3], args.Length > 4 ? args[4] : null);
        if (args.Length == 2 && args[0] == "info") return Info(args[1]);
        if (args.Length == 3 && args[0] == "listar") return Listar(args[1], args[2]);
        if (args.Length == 4 && args[0] == "sacar") return Sacar(args[1], args[2], args[3]);
        if (args.Length == 4 && args[0] == "entradas") return Entradas(args[1], args[2], args[3]);
        if (args.Length == 4 && args[0] == "manifiestos") return Manifiestos(args[1], args[2], args[3]);
        if (args.Length >= 4 && args[0] == "extraer") return Extraer(args[1], args[2], args[3..]);
        if (args.Length >= 3 && args[0] == "mundo") return Mundo(args[1], args[2..]);
        if (args.Length != 3) { Console.Error.WriteLine("uso: cwtool xml|rpf <entrada> <salida>"); return 1; }
        if (args[0] == "xml") return Xml(args[1], args[2]);
        if (args[0] == "rpf") return Rpf(args[1], args[2]);
        Console.Error.WriteLine("orden desconocida: " + args[0]);
        return 1;
    }

    static int Xml(string entrada, string salida)
    {
        Directory.CreateDirectory(salida);
        int hechos = 0, fallos = 0;
        foreach (var ruta in Directory.GetFiles(entrada, "*.xml"))
        {
            var nombre = Path.GetFileName(ruta);
            var formato = XmlMeta.GetXMLFormat(nombre.ToLowerInvariant(), out int recorte);
            if (formato == MetaFormat.XML) continue;
            try
            {
                var doc = new XmlDocument();
                doc.Load(ruta);
                // Las texturas (.dds) van en una carpeta con el nombre del archivo sin .xml
                var datos = XmlMeta.GetData(doc, formato, Path.Combine(entrada, nombre.Substring(0, nombre.Length - recorte)));
                if (datos == null) throw new Exception("CodeWalker no devolvió datos");
                File.WriteAllBytes(Path.Combine(salida, nombre.Substring(0, nombre.Length - recorte)), datos);
                hechos++;
            }
            catch (Exception e)
            {
                Console.Error.WriteLine(nombre + ": " + e.Message);
                fallos++;
            }
        }
        Console.WriteLine($"XML: {hechos} convertidos, {fallos} con error");
        return fallos == 0 ? 0 : 2;
    }

    // Carga el juego como CodeWalker (con DLC y carpeta mods) y dice si encuentra nuestros ymap,
    // arquetipos y modelos: así se ve en qué paso se pierde el mapa sin tener que abrir el juego.
    static int Mundo(string gta, string[] nombres)
    {
        GTA5Keys.LoadFromPath(gta, false, null);
        var gfc = new GameFileCache(512L * 1024 * 1024, 60, gta, false, "bcn", true, "");
        gfc.LoadArchetypes = true;
        gfc.Init(s => { }, e => Console.WriteLine("ERROR " + e));
        Console.WriteLine("DLC cargados (últimos): " + string.Join(", ", gfc.DlcNameList.GetRange(Math.Max(0, gfc.DlcNameList.Count - 4), Math.Min(4, gfc.DlcNameList.Count))));
        foreach (var s in gfc.DlcSetupFiles)
            if (s.DlcFile != null && s.DlcFile.Path.ToLowerInvariant().Contains("\\bcn\\"))
            {
                Console.WriteLine($"setup bcn: device={s.deviceName} order={s.order} ruta={s.DlcFile.Path}");
                foreach (var df in s.ContentFile.dataFiles) Console.WriteLine($"  datafile {df.filename} {df.fileType}");
                foreach (var cs in s.ContentFile.contentChangeSets)
                    Console.WriteLine($"  changeset {cs.changeSetName}: {string.Join(", ", (IEnumerable<string>)cs.filesToEnable ?? new string[0])}");
            }
        foreach (var n in nombres)
        {
            if (n == "edificios")  // edificios del juego (drawable, lejanos) para comparar con los nuestros
            {
                var campo = typeof(GameFileCache).GetField("archetypeDict", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
                var dic = (Dictionary<uint, Archetype>)campo.GetValue(gfc);
                foreach (var ar1 in dic.Values.Where(x => x._BaseArchetypeDef.assetType == rage__fwArchetypeDef__eAssetType.ASSET_TYPE_DRAWABLE
                                                         && x._BaseArchetypeDef.bsRadius > 25 && x._BaseArchetypeDef.lodDist < 250 && x._BaseArchetypeDef.lodDist > 100 && !x.Name.Contains("lod") && x.GetType() == typeof(Archetype)).Take(8))
                {
                    var d1 = ar1._BaseArchetypeDef;
                    Console.WriteLine($"  {ar1.Name}: flags=0x{d1.flags:X} lod={d1.lodDist} hdtex={d1.hdTextureDist} txd={JenkIndex.GetString(d1.textureDictionary)} phys={JenkIndex.GetString(d1.physicsDictionary)} special={d1.specialAttribute} bs={d1.bsRadius}");
                }
                continue;
            }
            if (n.EndsWith(".ytyp"))  // ruta de un ytyp del juego: resume sus primeros arquetipos
            {
                var yt = gfc.RpfMan.GetFile<YtypFile>(n);
                foreach (var ar0 in (yt?.AllArchetypes ?? new Archetype[0]).Take(6))
                {
                    var d0 = ar0._BaseArchetypeDef;
                    Console.WriteLine($"  {ar0.Name}: tipo={ar0.GetType().Name} flags=0x{d0.flags:X} lod={d0.lodDist} hdtex={d0.hdTextureDist} txd={JenkIndex.GetString(d0.textureDictionary)} " +
                                      $"phys={JenkIndex.GetString(d0.physicsDictionary)} assetType={d0.assetType} special={d0.specialAttribute}");
                }
                continue;
            }
            uint h = JenkHash.GenHash(n.ToLowerInvariant());
            var ar = gfc.GetArchetype(h);
            if (ar != null)
            {
                var d = ar._BaseArchetypeDef;
                Console.WriteLine($"  {n}: tipo={ar.GetType().Name} flags=0x{d.flags:X} special={d.specialAttribute} lod={d.lodDist} hdtex={d.hdTextureDist} " +
                                  $"txd={JenkIndex.GetString(d.textureDictionary)} phys={JenkIndex.GetString(d.physicsDictionary)} clip={JenkIndex.GetString(d.clipDictionary)} " +
                                  $"dd={JenkIndex.GetString(d.drawableDictionary)} asset={JenkIndex.GetString(d.assetName)} assetType={d.assetType} bs={d.bsRadius} ext={d.extensions.Count1}");
            }
            Console.WriteLine($"{n}: ymap={(gfc.YmapDict.ContainsKey(h) ? gfc.YmapDict[h].Path : "NO")} " +
                              $"arquetipo={(gfc.GetArchetype(h) != null ? "sí" : "NO")} ydr={(gfc.GetYdrEntry(h)?.Path ?? "NO")}");
        }
        return 0;
    }

    static int Extraer(string gta, string salida, string[] modelos)
    {
        GTA5Keys.LoadFromPath(gta, false, null);
        var gfc = new GameFileCache(512L * 1024 * 1024, 60, gta, false, "", false, "");
        gfc.Init(s => { }, e => Console.WriteLine("ERROR " + e));
        Directory.CreateDirectory(salida);
        int fallos = 0;
        foreach (var m in modelos)
        {
            var e = gfc.GetYdrEntry(JenkHash.GenHash(m.ToLowerInvariant()));
            if (e == null) { Console.WriteLine(m + ": no hay ydr"); fallos++; continue; }
            var xml = MetaXml.GetXml(e, e.File.ExtractFile(e), out string nombre, salida);
            File.WriteAllText(Path.Combine(salida, nombre), xml);
            Console.WriteLine($"{m}: {e.Path} -> {nombre}");
        }
        return fallos == 0 ? 0 : 2;
    }

    // Lista los archivos de los RPF del juego cuya ruta contiene 'filtro'
    static int Listar(string gta, string filtro)
    {
        GTA5Keys.LoadFromPath(gta, false, null);
        var rm = new RpfManager();
        rm.Init(gta, false, s => { }, e => { });
        foreach (var rpf in rm.AllRpfs)
            foreach (var e in rpf.AllEntries.OfType<RpfFileEntry>().Where(x => x.Path.Contains(filtro, StringComparison.OrdinalIgnoreCase)))
                Console.WriteLine($"{e.Path} {e.GetType().Name} {e.FileSize}");
        return 0;
    }

    // Copia tal cual un archivo de dentro de los RPF del juego (ruta como la escribe CodeWalker)
    static int Sacar(string gta, string ruta, string salida)
    {
        GTA5Keys.LoadFromPath(gta, false, null);
        var rm = new RpfManager();
        rm.Init(gta, false, s => { }, e => { });
        if (ruta.StartsWith("*"))  // *nombre: todos los que se llamen así, a salida_N
        {
            int n = 0;
            foreach (var rpf in rm.AllRpfs)
                foreach (var f in rpf.AllEntries.OfType<RpfFileEntry>().Where(x => x.NameLower == ruta.Substring(1)))
                {
                    File.WriteAllText($"{salida}_{n++}.txt", f.Path + "\n" + System.Text.Encoding.UTF8.GetString(f.File.ExtractFile(f)));
                }
            Console.WriteLine($"{n} archivos");
            return 0;
        }
        var e = rm.GetEntry(ruta) as RpfFileEntry;
        if (e == null) { Console.WriteLine("no está: " + ruta); return 2; }
        if (salida.EndsWith(".xml")) File.WriteAllText(salida, MetaXml.GetXml(e, e.File.ExtractFile(e), out _));
        else File.WriteAllBytes(salida, e.File.ExtractFile(e));
        return 0;
    }

    // Cómo están guardadas en los RPF las entradas cuyo nombre acaba en 'ext' (juego + nuestro dlc.rpf)
    static int Entradas(string gta, string nuestro, string ext)
    {
        GTA5Keys.LoadFromPath(gta, false, null);
        var rm = new RpfManager();
        rm.Init(gta, false, s => { }, e => { });
        var nuestroRpf = new RpfFile(nuestro, Path.GetFileName(nuestro));
        nuestroRpf.ScanStructure(s => { }, e => Console.WriteLine("ERROR " + e));
        int n = 0;
        foreach (var rpf in rm.AllRpfs.Take(100000).Concat(nuestroRpf.Children.Prepend(nuestroRpf)))
            foreach (var e in rpf.AllEntries.OfType<RpfFileEntry>())
            {
                if (!e.Name.EndsWith(ext, StringComparison.OrdinalIgnoreCase)) continue;
                if (e is RpfBinaryFileEntry b)
                    Console.WriteLine($"{e.Path}: binario size={b.FileSize} sin_comprimir={b.FileUncompressedSize} cifrado={b.IsEncrypted} " +
                                      $"enc_tipo={b.EncryptionType} rpf_enc={rpf.Encryption}");
                else
                    Console.WriteLine($"{e.Path}: recurso {e.GetType().Name}");
                if (++n > 6 && !rpf.Path.Contains("bcn")) break;
            }
        return 0;
    }

    // Saca a XML los _manifest.ymf de los DLC del juego cuya ruta contiene 'filtro' (para copiar su formato)
    static int Manifiestos(string gta, string salida, string filtro)
    {
        GTA5Keys.LoadFromPath(gta, false, null);
        var rm = new RpfManager();
        rm.Init(gta, false, s => { }, e => { });
        Directory.CreateDirectory(salida);
        int n = 0;
        foreach (var rpf in rm.AllRpfs)
            foreach (var e in rpf.AllEntries.OfType<RpfFileEntry>())
            {
                if (!e.Name.EndsWith(".ymf", StringComparison.OrdinalIgnoreCase) || !e.Path.Contains(filtro)) continue;
                var xml = MetaXml.GetXml(e, e.File.ExtractFile(e), out string nombre, salida);
                var destino = Path.Combine(salida, $"{n++}_{nombre}");
                File.WriteAllText(destino, xml);
                File.WriteAllBytes(Path.Combine(salida, $"{n - 1}_original.ymf"), e.File.ExtractFile(e));
                Console.WriteLine($"{e.Path} -> {destino} ({xml.Length} car.)");
                if (n >= 2000) return 0;
            }
        return 0;
    }

    // Lee un binario del juego y resume lo que contiene (para comprobar lo que generamos)
    static int Info(string ruta)
    {
        var datos = File.ReadAllBytes(ruta);
        var nombre = Path.GetFileName(ruta);
        var ext = Path.GetExtension(ruta).ToLowerInvariant();
        if (ext == ".ymf")  // vuelta a XML: debe salir igual que el XML de partida
        {
            var y = new YmfFile();
            y.Load(datos, new RpfBinaryFileEntry { Name = nombre, NameLower = nombre.ToLowerInvariant() });
            Console.WriteLine(y.Pso != null ? PsoXml.GetXml(y.Pso) : "no es PSO");
        }
        else if (ext == ".ymap")
        {
            var y = new YmapFile();
            y.Load(datos);
            var d = y._CMapData;
            Console.WriteLine($"{nombre}: name={JenkIndex.GetString(d.name)} flags={d.flags} contentFlags={d.contentFlags} entidades={y.AllEntities?.Length ?? 0}");
            Console.WriteLine($"  streaming {d.streamingExtentsMin} .. {d.streamingExtentsMax}");
            foreach (var e in y.AllEntities ?? new YmapEntityDef[0])
                Console.WriteLine($"  {e._CEntityDef.archetypeName} pos={e._CEntityDef.position} lod={e._CEntityDef.lodDist} flags={e._CEntityDef.flags}");
        }
        else if (ext == ".ytyp")
        {
            var y = new YtypFile();
            y.Load(datos);
            Console.WriteLine($"{nombre}: name={JenkIndex.GetString(y._CMapTypes.name)} arquetipos={y.AllArchetypes?.Length ?? 0}");
            foreach (var a in y.AllArchetypes ?? new Archetype[0])
                Console.WriteLine($"  {a.Name} txd={JenkIndex.GetString(a._BaseArchetypeDef.textureDictionary)} asset={JenkIndex.GetString(a._BaseArchetypeDef.assetName)} lod={a.LodDist} bb={a.BBMin}..{a.BBMax}");
        }
        else if (ext == ".ydr")
        {
            var y = new YdrFile();
            RpfFile.LoadResourceFile(y, datos, 165);
            var dr = y.Drawable;
            Console.WriteLine($"{nombre}: name={dr?.Name} bb={dr?.BoundingBoxMin}..{dr?.BoundingBoxMax} modelos={dr?.AllModels?.Length}");
            foreach (var s in dr?.ShaderGroup?.Shaders?.data_items ?? new ShaderFX[0])
                Console.WriteLine($"  shader {s.Name} ({s.FileName})");
        }
        else if (ext == ".ytd")
        {
            var y = new YtdFile();
            RpfFile.LoadResourceFile(y, datos, 13);
            foreach (var t in y.TextureDict?.Textures?.data_items ?? new Texture[0])
                Console.WriteLine($"  {t.Name} {t.Width}x{t.Height} {t.Format}");
        }
        return 0;
    }

    static int DlcList(string gta, string destino, string pack)
    {
        destino = Path.GetFullPath(destino);
        if (!File.Exists(destino))
        {
            Directory.CreateDirectory(Path.GetDirectoryName(destino));
            File.Copy(Path.Combine(gta, "update", "update.rpf"), destino);
        }
        GTA5Keys.LoadFromPath(gta, false, null);
        var rpf = new RpfFile(destino, Path.GetFileName(destino));
        rpf.ScanStructure(null, e => Console.Error.WriteLine(e));
        RpfFileEntry entrada = null;
        foreach (var e in rpf.AllEntries)
            if (e is RpfFileEntry fe && fe.Path.Replace('/', '\\').EndsWith(@"common\data\dlclist.xml", StringComparison.OrdinalIgnoreCase))
                entrada = fe;
        if (entrada == null) { Console.Error.WriteLine(@"no se encuentra common\data\dlclist.xml"); return 3; }
        var texto = System.Text.Encoding.UTF8.GetString(rpf.ExtractFile(entrada)).TrimStart('\uFEFF');
        var linea = $"dlcpacks:/{pack}/";
        if (texto.Contains(linea)) { Console.WriteLine("ya estaba: " + linea); return 0; }
        int fin = texto.LastIndexOf("</Paths>", StringComparison.OrdinalIgnoreCase);
        if (fin < 0) { Console.Error.WriteLine("dlclist.xml sin </Paths>"); return 4; }
        texto = texto.Substring(0, fin) + $"\t<Item>{linea}</Item>\r\n\t" + texto.Substring(fin);
        // CodeWalker solo escribe RPF sin cifrar (OPEN, como OpenIV): se pasa la copia y sus padres a OPEN
        RpfFile.EnsureValidEncryption(entrada.File, null);
        RpfFile.CreateFile(entrada.Parent, entrada.Name, System.Text.Encoding.UTF8.GetBytes(texto), true);
        Console.WriteLine("añadido " + linea + " en " + destino);
        return 0;
    }

    static int Rpf(string carpeta, string archivo)
    {
        archivo = Path.GetFullPath(archivo);
        if (File.Exists(archivo)) File.Delete(archivo);
        var rpf = RpfFile.CreateNew(Path.GetDirectoryName(archivo), Path.GetFileName(archivo));
        int n = Llenar(rpf.Root, carpeta);
        Console.WriteLine($"RPF: {n} archivos en {archivo}");
        return 0;
    }

    // Lo contrario de 'rpf': saca un RPF a carpeta (los RPF anidados como subcarpetas .rpf, los recursos con su
    // cabecera, tal como los lee 'rpf'); 'omitir' es una expresión regular de nombres que no se sacan
    static int Abrir(string gta, string archivo, string carpeta, string omitir)
    {
        GTA5Keys.LoadFromPath(gta, false, null);
        var rpf = new RpfFile(Path.GetFullPath(archivo), Path.GetFileName(archivo));
        rpf.ScanStructure(s => { }, e => Console.Error.WriteLine(e));
        var re = omitir == null ? null : new System.Text.RegularExpressions.Regex(omitir);
        int n = 0, fuera = 0;
        // Nombres de verdad: los RPF hechos con más de 64 KB de nombres tienen el puntero (16 bits) desbordado,
        // pero los nombres están todos en la tabla, seguidos y en el orden de las entradas (sin repetidos)
        var nombre = new Dictionary<RpfEntry, string>();
        void Nombres(RpfFile f)
        {
            using var br = new BinaryReader(File.OpenRead(f.GetPhysicalFilePath()));
            br.BaseStream.Position = f.StartPos + 16 + f.EntryCount * 16;
            var tabla = br.ReadBytes((int)f.NamesLength);
            var lista = new List<string>();
            int ini = 0;
            for (int i = 0; i < tabla.Length && lista.Count < f.EntryCount; i++)
                if (tabla[i] == 0) { lista.Add(System.Text.Encoding.UTF8.GetString(tabla, ini, i - ini)); ini = i + 1; }
            if (lista.Count != f.AllEntries.Count) throw new Exception($"{f.Name}: {lista.Count} nombres para {f.AllEntries.Count} entradas");
            int malos = 0;
            for (int i = 0; i < lista.Count; i++)
            {
                if (f.AllEntries[i].Name != lista[i]) malos++;
                nombre[f.AllEntries[i]] = lista[i];
            }
            if (malos > 0) Console.WriteLine($"{f.Name}: {malos} nombres desbordados recuperados");
            foreach (var c in f.Children ?? new List<RpfFile>()) Nombres(c);
        }
        Nombres(rpf);
        void Sacar(RpfFile f, RpfDirectoryEntry dir, string destino)
        {
            Directory.CreateDirectory(destino);
            foreach (var d in dir.Directories) Sacar(f, d, Path.Combine(destino, d.Name));
            foreach (var e in dir.Files)
            {
                if (e.NameLower.EndsWith(".rpf"))
                {
                    var hijo = f.Children.First(c => c.Name == e.Name && c.Path.StartsWith(e.Path, StringComparison.OrdinalIgnoreCase));
                    Sacar(hijo, hijo.Root, Path.Combine(destino, e.Name));
                    continue;
                }
                var real = nombre[e];
                if (re != null && re.IsMatch(real)) { fuera++; continue; }
                var datos = f.ExtractFile(e);
                if (e is RpfResourceFileEntry rr) datos = ResourceBuilder.AddResourceHeader(rr, ResourceBuilder.Compress(datos));
                File.WriteAllBytes(Path.Combine(destino, real), datos);
                n++;
            }
        }
        Sacar(rpf, rpf.Root, carpeta);
        Console.WriteLine($"{n} archivos sacados, {fuera} omitidos");
        return 0;
    }

    static int Llenar(RpfDirectoryEntry dir, string carpeta)
    {
        int n = 0;
        foreach (var sub in Directory.GetDirectories(carpeta))
        {
            var nombre = Path.GetFileName(sub);
            var destino = nombre.EndsWith(".rpf", StringComparison.OrdinalIgnoreCase)
                ? RpfFile.CreateNew(dir, nombre).Root
                : RpfFile.CreateDirectory(dir, nombre);
            n += Llenar(destino, sub);
        }
        foreach (var f in Directory.GetFiles(carpeta))
        {
            RpfFile.CreateFile(dir, Path.GetFileName(f), File.ReadAllBytes(f));
            n++;
        }
        return n;
    }
}
