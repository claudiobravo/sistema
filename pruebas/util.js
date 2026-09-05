// Utilidades comunes a las pruebas del Sistema.
var fs=require('fs'), path=require('path');

var fallos=0, aciertos=0;
function chk(nombre,cond,extra){
  if(cond){ aciertos++; console.log('  ok  '+nombre); }
  else { fallos++; console.log('  FALLA '+nombre+(extra!==undefined?'  → '+JSON.stringify(extra):'')); }
}
function seccion(t){ console.log('\n== '+t+' =='); }
function resumen(){
  console.log('\n'+(fallos?('FALLOS: '+fallos):'TODO OK')+'  ('+(aciertos+fallos)+' comprobaciones)');
  process.exit(fallos?1:0);
}
function sumarFallo(){ fallos++; }

var APP='file://'+path.join(__dirname,'..','index.html');

// Chromium: el de Playwright si está, o el que indique la variable CHROMIUM.
function chromium(){
  var c=[process.env.CHROMIUM,
         '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
         '/opt/pw-browsers/chromium/chrome-linux/chrome',
         '/usr/bin/chromium','/usr/bin/google-chrome'].filter(Boolean);
  return c.find(function(p){return fs.existsSync(p);});   // undefined = que lo busque Playwright
}

// Abre la app en una página limpia y recoge cualquier error de consola.
async function abrir(){
  var pw;
  try{ pw=require('playwright-core'); }
  catch(e){
    console.log('Falta playwright-core. Instálalo con:  npm i playwright-core');
    process.exit(2);
  }
  var nav=await pw.chromium.launch({executablePath:chromium(),args:['--no-sandbox']});
  var pg=await nav.newPage({viewport:{width:390,height:844}});
  var errores=[];
  pg.on('console',function(m){ if(m.type()==='error') errores.push(m.text()); });
  pg.on('pageerror',function(e){ errores.push('pageerror: '+e.message); });
  await pg.goto(APP);
  await pg.waitForTimeout(600);
  return {nav:nav,pg:pg,errores:errores};
}
function comprobarConsola(errores){
  console.log('\nerrores de consola:', errores.length?errores:'ninguno');
  if(errores.length) sumarFallo();
}

// Fechas, para no clavar días concretos en las pruebas.
function iso(d){return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');}
function hoy(){return iso(new Date());}
function hace(n){var d=new Date(); d.setDate(d.getDate()-n); return iso(d);}

module.exports={chk:chk,seccion:seccion,resumen:resumen,sumarFallo:sumarFallo,
  abrir:abrir,comprobarConsola:comprobarConsola,APP:APP,iso:iso,hoy:hoy,hace:hace};
