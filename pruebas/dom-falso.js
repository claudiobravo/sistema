// DOM mínimo para poder cargar la app en Node, sin navegador.
// No pinta nada: solo aguanta las llamadas para que se pueda ejercitar la
// lógica (sincronización, EXP, fusión). Lo visual se prueba en Chromium,
// en dias.test.js y puertas.test.js.
function El(id){
  return {
    id:id, value:'', textContent:'', innerHTML:'', className:'', tagName:'DIV',
    style:{setProperty(){},removeProperty(){},getPropertyValue(){return ''}},
    dataset:{}, files:null, checked:false,
    setAttribute(){}, getAttribute(){return null}, removeAttribute(){},
    classList:{add(){},remove(){},toggle(){},contains(){return false}},
    addEventListener(t,f){ (this._h||(this._h={}))[t]=f; },
    insertAdjacentHTML(){}, click(){}, closest(){return null},
    querySelectorAll(){return []}
  };
}
const els={};
global.document={
  getElementById(id){ return els[id]||(els[id]=El(id)); },
  querySelectorAll(){ return []; },
  addEventListener(){}, get activeElement(){return null}, hidden:false
};
global.window={ addEventListener(){}, scrollTo(){} };
const mem={};
global.localStorage={ getItem:k=>k in mem?mem[k]:null, setItem:(k,v)=>{mem[k]=String(v)}, removeItem:k=>{delete mem[k]} };
// Ojo: Node trae su propio `navigator` de solo lectura. Un `global.navigator = {...}`
// se traga sin error y deja onLine en undefined, o sea, la app se creería
// siempre sin cobertura. Hay que definirlo a mano.
Object.defineProperty(globalThis,'navigator',{value:{onLine:true},writable:true,configurable:true});
global.alert=()=>{};
global.FileReader=function(){};
module.exports={els:els,mem:mem};
