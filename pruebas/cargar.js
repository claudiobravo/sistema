// Carga el <script> de index.html en este proceso, con un DOM falso puesto,
// y deja a la vista sus funciones internas para poder examinarlas.
// Así las pruebas van siempre contra el fichero real, no contra una copia.
var fs=require('fs'), path=require('path'), vm=require('vm');
require('./dom-falso.js');

var html=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
var i=html.indexOf('<script>')+'<script>'.length, j=html.indexOf('</script>');
if(i<8||j<0) throw new Error('no encuentro el <script> de index.html');
var app=html.slice(i,j);

var marca="if('serviceWorker' in navigator)";
var k=app.indexOf(marca);
if(k<0) throw new Error('no encuentro el registro del service worker');
app=app.slice(0,k)+
  "global.__T={S:S,SYNC:SYNC,fundir:fundir,fundirPuertas:fundirPuertas,diaVacio:diaVacio,"+
  "sincronizar:sincronizar,exp:exp,misionCompleta:misionCompleta,guardar:guardar,hoyISO:hoyISO};\n"+
  app.slice(k);

vm.runInThisContext(app,{filename:'index.html (script)'});
module.exports=global.__T;
