const dt=function(){const e=document.createElement("link").relList;if(e&&e.supports&&e.supports("modulepreload"))return;for(const o of document.querySelectorAll('link[rel="modulepreload"]'))s(o);new MutationObserver(o=>{for(const r of o)if(r.type==="childList")for(const i of r.addedNodes)i.tagName==="LINK"&&i.rel==="modulepreload"&&s(i)}).observe(document,{childList:!0,subtree:!0});function n(o){const r={};return o.integrity&&(r.integrity=o.integrity),o.referrerpolicy&&(r.referrerPolicy=o.referrerpolicy),o.crossorigin==="use-credentials"?r.credentials="include":o.crossorigin==="anonymous"?r.credentials="omit":r.credentials="same-origin",r}function s(o){if(o.ep)return;o.ep=!0;const r=n(o);fetch(o.href,r)}};dt();function E(){}function V(t,e){for(const n in e)t[n]=e[n];return t}function Je(t){return t()}function Re(){return Object.create(null)}function U(t){t.forEach(Je)}function Ce(t){return typeof t=="function"}function H(t,e){return t!=t?e==e:t!==e||t&&typeof t=="object"||typeof t=="function"}function _t(t){return Object.keys(t).length===0}function je(t,...e){if(t==null)return E;const n=t.subscribe(...e);return n.unsubscribe?()=>n.unsubscribe():n}function ht(t){let e;return je(t,n=>e=n)(),e}function A(t,e,n){t.$$.on_destroy.push(je(e,n))}function Qe(t,e,n,s){if(t){const o=xe(t,e,n,s);return t[0](o)}}function xe(t,e,n,s){return t[1]&&s?V(n.ctx.slice(),t[1](s(e))):n.ctx}function Ve(t,e,n,s){if(t[2]&&s){const o=t[2](s(n));if(e.dirty===void 0)return o;if(typeof o=="object"){const r=[],i=Math.max(e.dirty.length,o.length);for(let c=0;c<i;c+=1)r[c]=e.dirty[c]|o[c];return r}return e.dirty|o}return e.dirty}function We(t,e,n,s,o,r){if(o){const i=xe(e,n,s,r);t.p(i,o)}}function Xe(t){if(t.ctx.length>32){const e=[],n=t.ctx.length/32;for(let s=0;s<n;s++)e[s]=-1;return e}return-1}function Le(t){const e={};for(const n in t)n[0]!=="$"&&(e[n]=t[n]);return e}function Me(t){return t??""}function Ze(t,e,n){return t.set(n),e}function et(t){return t&&Ce(t.destroy)?t.destroy:E}function b(t,e){t.appendChild(e)}function M(t,e,n){t.insertBefore(e,n||null)}function R(t){t.parentNode.removeChild(t)}function w(t){return document.createElement(t)}function q(t){return document.createTextNode(t)}function N(){return q(" ")}function X(){return q("")}function re(t,e,n,s){return t.addEventListener(e,n,s),()=>t.removeEventListener(e,n,s)}function tt(t){return function(e){return e.preventDefault(),t.call(this,e)}}function v(t,e,n){n==null?t.removeAttribute(e):t.getAttribute(e)!==n&&t.setAttribute(e,n)}function pt(t){return Array.from(t.childNodes)}function fe(t,e){e=""+e,t.wholeText!==e&&(t.data=e)}function le(t,e){t.value=e??""}function Te(t,e,n){t.classList[n?"add":"remove"](e)}let W;function x(t){W=t}function G(){if(!W)throw new Error("Function called outside component initialization");return W}function mt(t){G().$$.before_update.push(t)}function Oe(t){G().$$.on_mount.push(t)}function gt(t){G().$$.after_update.push(t)}function yt(t){G().$$.on_destroy.push(t)}function Pe(t,e){return G().$$.context.set(t,e),e}function ce(t){return G().$$.context.get(t)}const Q=[],ie=[],se=[],Ae=[],bt=Promise.resolve();let me=!1;function kt(){me||(me=!0,bt.then(nt))}function ge(t){se.push(t)}const _e=new Set;let ne=0;function nt(){const t=W;do{for(;ne<Q.length;){const e=Q[ne];ne++,x(e),vt(e.$$)}for(x(null),Q.length=0,ne=0;ie.length;)ie.pop()();for(let e=0;e<se.length;e+=1){const n=se[e];_e.has(n)||(_e.add(n),n())}se.length=0}while(Q.length);for(;Ae.length;)Ae.pop()();me=!1,_e.clear(),x(t)}function vt(t){if(t.fragment!==null){t.update(),U(t.before_update);const e=t.dirty;t.dirty=[-1],t.fragment&&t.fragment.p(t.ctx,e),t.after_update.forEach(ge)}}const oe=new Set;let K;function Z(){K={r:0,c:[],p:K}}function ee(){K.r||U(K.c),K=K.p}function C(t,e){t&&t.i&&(oe.delete(t),t.i(e))}function j(t,e,n,s){if(t&&t.o){if(oe.has(t))return;oe.add(t),K.c.push(()=>{oe.delete(t),s&&(n&&t.d(1),s())}),t.o(e)}}function wt(t,e){t.d(1),e.delete(t.key)}function St(t,e){j(t,1,1,()=>{e.delete(t.key)})}function st(t,e,n,s,o,r,i,c,l,u,h,a){let _=t.length,p=r.length,f=_;const d={};for(;f--;)d[t[f].key]=f;const m=[],O=new Map,T=new Map;for(f=p;f--;){const g=a(o,r,f),S=n(g);let P=i.get(S);P?s&&P.p(g,e):(P=u(S,g),P.c()),O.set(S,m[f]=P),S in d&&T.set(S,Math.abs(f-d[S]))}const L=new Set,k=new Set;function y(g){C(g,1),g.m(c,h),i.set(g.key,g),h=g.first,p--}for(;_&&p;){const g=m[p-1],S=t[_-1],P=g.key,J=S.key;g===S?(h=g.first,_--,p--):O.has(J)?!i.has(P)||L.has(P)?y(g):k.has(J)?_--:T.get(P)>T.get(J)?(k.add(P),y(g)):(L.add(J),_--):(l(S,i),_--)}for(;_--;){const g=t[_];O.has(g.key)||l(g,i)}for(;p;)y(m[p-1]);return m}function ot(t,e){const n={},s={},o={$$scope:1};let r=t.length;for(;r--;){const i=t[r],c=e[r];if(c){for(const l in i)l in c||(s[l]=1);for(const l in c)o[l]||(n[l]=c[l],o[l]=1);t[r]=c}else for(const l in i)o[l]=1}for(const i in s)i in n||(n[i]=void 0);return n}function ye(t){return typeof t=="object"&&t!==null?t:{}}function D(t){t&&t.c()}function $(t,e,n,s){const{fragment:o,on_mount:r,on_destroy:i,after_update:c}=t.$$;o&&o.m(e,n),s||ge(()=>{const l=r.map(Je).filter(Ce);i?i.push(...l):U(l),t.$$.on_mount=[]}),c.forEach(ge)}function I(t,e){const n=t.$$;n.fragment!==null&&(U(n.on_destroy),n.fragment&&n.fragment.d(e),n.on_destroy=n.fragment=null,n.ctx=[])}function Ct(t,e){t.$$.dirty[0]===-1&&(Q.push(t),kt(),t.$$.dirty.fill(0)),t.$$.dirty[e/31|0]|=1<<e%31}function B(t,e,n,s,o,r,i,c=[-1]){const l=W;x(t);const u=t.$$={fragment:null,ctx:null,props:r,update:E,not_equal:o,bound:Re(),on_mount:[],on_destroy:[],on_disconnect:[],before_update:[],after_update:[],context:new Map(e.context||(l?l.$$.context:[])),callbacks:Re(),dirty:c,skip_bound:!1,root:e.target||l.$$.root};i&&i(u.root);let h=!1;if(u.ctx=n?n(t,e.props||{},(a,_,...p)=>{const f=p.length?p[0]:_;return u.ctx&&o(u.ctx[a],u.ctx[a]=f)&&(!u.skip_bound&&u.bound[a]&&u.bound[a](f),h&&Ct(t,a)),_}):[],u.update(),h=!0,U(u.before_update),u.fragment=s?s(u.ctx):!1,e.target){if(e.hydrate){const a=pt(e.target);u.fragment&&u.fragment.l(a),a.forEach(R)}else u.fragment&&u.fragment.c();e.intro&&C(t.$$.fragment),$(t,e.target,e.anchor,e.customElement),nt()}x(l)}class F{$destroy(){I(this,1),this.$destroy=E}$on(e,n){const s=this.$$.callbacks[e]||(this.$$.callbacks[e]=[]);return s.push(n),()=>{const o=s.indexOf(n);o!==-1&&s.splice(o,1)}}$set(e){this.$$set&&!_t(e)&&(this.$$.skip_bound=!0,this.$$set(e),this.$$.skip_bound=!1)}}const Y=[];function jt(t,e){return{subscribe:z(t,e).subscribe}}function z(t,e=E){let n;const s=new Set;function o(c){if(H(t,c)&&(t=c,n)){const l=!Y.length;for(const u of s)u[1](),Y.push(u,t);if(l){for(let u=0;u<Y.length;u+=2)Y[u][0](Y[u+1]);Y.length=0}}}function r(c){o(c(t))}function i(c,l=E){const u=[c,l];return s.add(u),s.size===1&&(n=e(o)||E),c(t),()=>{s.delete(u),s.size===0&&(n(),n=null)}}return{set:o,update:r,subscribe:i}}function te(t,e,n){const s=!Array.isArray(t),o=s?[t]:t,r=e.length<2;return jt(n,i=>{let c=!1;const l=[];let u=0,h=E;const a=()=>{if(u)return;h();const p=e(s?l[0]:l,i);r?i(p):h=Ce(p)?p:E},_=o.map((p,f)=>je(p,d=>{l[f]=d,u&=~(1<<f),c&&a()},()=>{u|=1<<f}));return c=!0,a(),function(){U(_),h()}})}const be={},ke={};function he(t){return{...t.location,state:t.history.state,key:t.history.state&&t.history.state.key||"initial"}}function Ot(t,e){const n=[];let s=he(t);return{get location(){return s},listen(o){n.push(o);const r=()=>{s=he(t),o({location:s,action:"POP"})};return t.addEventListener("popstate",r),()=>{t.removeEventListener("popstate",r);const i=n.indexOf(o);n.splice(i,1)}},navigate(o,{state:r,replace:i=!1}={}){r={...r,key:Date.now()+""};try{i?t.history.replaceState(r,null,o):t.history.pushState(r,null,o)}catch{t.location[i?"replace":"assign"](o)}s=he(t),n.forEach(c=>c({location:s,action:"PUSH"}))}}}function Et(t="/"){let e=0;const n=[{pathname:t,search:""}],s=[];return{get location(){return n[e]},addEventListener(o,r){},removeEventListener(o,r){},history:{get entries(){return n},get index(){return e},get state(){return s[e]},pushState(o,r,i){const[c,l=""]=i.split("?");e++,n.push({pathname:c,search:l}),s.push(o)},replaceState(o,r,i){const[c,l=""]=i.split("?");n[e]={pathname:c,search:l},s[e]=o}}}}const Nt=Boolean(typeof window<"u"&&window.document&&window.document.createElement),ve=Ot(Nt?window:Et()),{navigate:rt}=ve,lt=/^:(.+)/,$e=4,Rt=3,Lt=2,Mt=1,Tt=1;function Pt(t){return t===""}function At(t){return lt.test(t)}function ct(t){return t[0]==="*"}function we(t){return t.replace(/(^\/+|\/+$)/g,"").split("/")}function pe(t){return t.replace(/(^\/+|\/+$)/g,"")}function $t(t,e){const n=t.default?0:we(t.path).reduce((s,o)=>(s+=$e,Pt(o)?s+=Tt:At(o)?s+=Lt:ct(o)?s-=$e+Mt:s+=Rt,s),0);return{route:t,score:n,index:e}}function It(t){return t.map($t).sort((e,n)=>e.score<n.score?1:e.score>n.score?-1:e.index-n.index)}function it(t,e){let n,s;const[o]=e.split("?"),r=we(o),i=r[0]==="",c=It(t);for(let l=0,u=c.length;l<u;l++){const h=c[l].route;let a=!1;if(h.default){s={route:h,params:{},uri:e};continue}const _=we(h.path),p={},f=Math.max(r.length,_.length);let d=0;for(;d<f;d++){const m=_[d],O=r[d];if(m!==void 0&&ct(m)){const L=m==="*"?"*":m.slice(1);p[L]=r.slice(d).map(decodeURIComponent).join("/");break}if(O===void 0){a=!0;break}let T=lt.exec(m);if(T&&!i){const L=decodeURIComponent(O);p[T[1]]=L}else if(m!==O){a=!0;break}}if(!a){n={route:h,params:p,uri:"/"+r.slice(0,d).join("/")};break}}return n||s||null}function zt(t,e){return it([t],e)}function Ie(t,e){return`${pe(e==="/"?t:`${pe(t)}/${pe(e)}`)}/`}function Dt(t){return!t.defaultPrevented&&t.button===0&&!(t.metaKey||t.altKey||t.ctrlKey||t.shiftKey)}function Ht(t){const e=location.host;return t.host==e||t.href.indexOf(`https://${e}`)===0||t.href.indexOf(`http://${e}`)===0}function Ut(t){let e;const n=t[9].default,s=Qe(n,t,t[8],null);return{c(){s&&s.c()},m(o,r){s&&s.m(o,r),e=!0},p(o,[r]){s&&s.p&&(!e||r&256)&&We(s,n,o,o[8],e?Ve(n,o[8],r,null):Xe(o[8]),null)},i(o){e||(C(s,o),e=!0)},o(o){j(s,o),e=!1},d(o){s&&s.d(o)}}}function Kt(t,e,n){let s,o,r,{$$slots:i={},$$scope:c}=e,{basepath:l="/"}=e,{url:u=null}=e;const h=ce(be),a=ce(ke),_=z([]);A(t,_,k=>n(6,o=k));const p=z(null);let f=!1;const d=h||z(u?{pathname:u}:ve.location);A(t,d,k=>n(5,s=k));const m=a?a.routerBase:z({path:l,uri:l});A(t,m,k=>n(7,r=k));const O=te([m,p],([k,y])=>{if(y===null)return k;const{path:g}=k,{route:S,uri:P}=y;return{path:S.default?g:S.path.replace(/\*.*$/,""),uri:P}});function T(k){const{path:y}=r;let{path:g}=k;if(k._path=g,k.path=Ie(y,g),typeof window>"u"){if(f)return;const S=zt(k,s.pathname);S&&(p.set(S),f=!0)}else _.update(S=>(S.push(k),S))}function L(k){_.update(y=>{const g=y.indexOf(k);return y.splice(g,1),y})}return h||(Oe(()=>ve.listen(y=>{d.set(y.location)})),Pe(be,d)),Pe(ke,{activeRoute:p,base:m,routerBase:O,registerRoute:T,unregisterRoute:L}),t.$$set=k=>{"basepath"in k&&n(3,l=k.basepath),"url"in k&&n(4,u=k.url),"$$scope"in k&&n(8,c=k.$$scope)},t.$$.update=()=>{if(t.$$.dirty&128){const{path:k}=r;_.update(y=>(y.forEach(g=>g.path=Ie(k,g._path)),y))}if(t.$$.dirty&96){const k=it(o,s.pathname);p.set(k)}},[_,d,m,l,u,s,o,r,c,i]}class qt extends F{constructor(e){super(),B(this,e,Kt,Ut,H,{basepath:3,url:4})}}const Bt=t=>({params:t&4,location:t&16}),ze=t=>({params:t[2],location:t[4]});function De(t){let e,n,s,o;const r=[Yt,Ft],i=[];function c(l,u){return l[0]!==null?0:1}return e=c(t),n=i[e]=r[e](t),{c(){n.c(),s=X()},m(l,u){i[e].m(l,u),M(l,s,u),o=!0},p(l,u){let h=e;e=c(l),e===h?i[e].p(l,u):(Z(),j(i[h],1,1,()=>{i[h]=null}),ee(),n=i[e],n?n.p(l,u):(n=i[e]=r[e](l),n.c()),C(n,1),n.m(s.parentNode,s))},i(l){o||(C(n),o=!0)},o(l){j(n),o=!1},d(l){i[e].d(l),l&&R(s)}}}function Ft(t){let e;const n=t[10].default,s=Qe(n,t,t[9],ze);return{c(){s&&s.c()},m(o,r){s&&s.m(o,r),e=!0},p(o,r){s&&s.p&&(!e||r&532)&&We(s,n,o,o[9],e?Ve(n,o[9],r,Bt):Xe(o[9]),ze)},i(o){e||(C(s,o),e=!0)},o(o){j(s,o),e=!1},d(o){s&&s.d(o)}}}function Yt(t){let e,n,s;const o=[{location:t[4]},t[2],t[3]];var r=t[0];function i(c){let l={};for(let u=0;u<o.length;u+=1)l=V(l,o[u]);return{props:l}}return r&&(e=new r(i())),{c(){e&&D(e.$$.fragment),n=X()},m(c,l){e&&$(e,c,l),M(c,n,l),s=!0},p(c,l){const u=l&28?ot(o,[l&16&&{location:c[4]},l&4&&ye(c[2]),l&8&&ye(c[3])]):{};if(r!==(r=c[0])){if(e){Z();const h=e;j(h.$$.fragment,1,0,()=>{I(h,1)}),ee()}r?(e=new r(i()),D(e.$$.fragment),C(e.$$.fragment,1),$(e,n.parentNode,n)):e=null}else r&&e.$set(u)},i(c){s||(e&&C(e.$$.fragment,c),s=!0)},o(c){e&&j(e.$$.fragment,c),s=!1},d(c){c&&R(n),e&&I(e,c)}}}function Gt(t){let e,n,s=t[1]!==null&&t[1].route===t[7]&&De(t);return{c(){s&&s.c(),e=X()},m(o,r){s&&s.m(o,r),M(o,e,r),n=!0},p(o,[r]){o[1]!==null&&o[1].route===o[7]?s?(s.p(o,r),r&2&&C(s,1)):(s=De(o),s.c(),C(s,1),s.m(e.parentNode,e)):s&&(Z(),j(s,1,1,()=>{s=null}),ee())},i(o){n||(C(s),n=!0)},o(o){j(s),n=!1},d(o){s&&s.d(o),o&&R(e)}}}function Jt(t,e,n){let s,o,{$$slots:r={},$$scope:i}=e,{path:c=""}=e,{component:l=null}=e;const{registerRoute:u,unregisterRoute:h,activeRoute:a}=ce(ke);A(t,a,m=>n(1,s=m));const _=ce(be);A(t,_,m=>n(4,o=m));const p={path:c,default:c===""};let f={},d={};return u(p),typeof window<"u"&&yt(()=>{h(p)}),t.$$set=m=>{n(13,e=V(V({},e),Le(m))),"path"in m&&n(8,c=m.path),"component"in m&&n(0,l=m.component),"$$scope"in m&&n(9,i=m.$$scope)},t.$$.update=()=>{t.$$.dirty&2&&s&&s.route===p&&n(2,f=s.params);{const{path:m,component:O,...T}=e;n(3,d=T)}},e=Le(e),[l,s,f,d,o,a,_,p,c,i,r]}class He extends F{constructor(e){super(),B(this,e,Jt,Gt,H,{path:8,component:0})}}function ut(t){function e(n){const s=n.currentTarget;s.target===""&&Ht(s)&&Dt(n)&&(n.preventDefault(),rt(s.pathname+s.search,{replace:s.hasAttribute("replace")}))}return t.addEventListener("click",e),{destroy(){t.removeEventListener("click",e)}}}function Qt(t){return new Promise(e=>setTimeout(e,t))}function xt(t,e=1e3){let n=t;return async function(){await Qt(n),n*=2}}async function at(t,e={}){const n=xt(100);let s=null;for(;;){try{s=await fetch(t,e)}catch{}if(s&&s.ok)return await s.json();await n()}}async function Vt(t,e){return await at(t,{method:"POST",headers:{"Content-type":"application/json"},body:JSON.stringify(e)})}async function Ee(t,e={}){return Object.keys(e).length&&(t=t+"?"+Object.entries(e).map(([n,s])=>`${n}=${s}`).join("&")),await at(t)}const ue=await Ee("/persona"),Ne=z(await Ee("/contacts")),ae=z(null),Ue=new Set,de=z([]),Se=z({}),Wt=te([de,Se],([t,e])=>t.filter(n=>!(n.nonce in e))),Xt=te([Ne,Wt],([t,e])=>{let n={};for(const s of t)n[s]=e.filter(o=>o.sender==s).length;return n}),Zt=te(de,t=>t.at(-1)?.nonce),en=te([de,ae],([t,e])=>t.filter(n=>n.sender==e||n.receiver==e));function ft(t){return t.length==0||t==ue?!1:(Ne.update(e=>e.includes(t)?e:(console.log("Adding new contact "+t),console.log("To contacts: "+e),e.concat(t))),!0)}async function tn(){const t=ht(Zt);let s=(await Ee("/messages",t?{since:t}:{})).filter(o=>!Ue.has(o.nonce));if(s.length>0){for(const o of s)Ue.add(o.nonce);de.update(o=>o.concat(s))}}setInterval(tn,250);function Ke(t,e,n){const s=t.slice();return s[6]=e[n],s}function qe(t){let e,n=t[3][t[6]]+"",s;return{c(){e=w("span"),s=q(n),v(e,"class","unread svelte-ah7idb")},m(o,r){M(o,e,r),b(e,s)},p(o,r){r&10&&n!==(n=o[3][o[6]]+"")&&fe(s,n)},d(o){o&&R(e)}}}function Be(t,e){let n,s,o=e[6]+"",r,i,c,l,u,h,a,_=e[3][e[6]]&&qe(e);return{key:t,first:null,c(){n=w("li"),s=w("a"),r=q(o),l=N(),_&&_.c(),u=N(),v(s,"href",i="/conversations/"+e[6]),v(s,"class","svelte-ah7idb"),v(n,"class","svelte-ah7idb"),Te(n,"current",e[6]===e[2]),this.first=n},m(p,f){M(p,n,f),b(n,s),b(s,r),b(n,l),_&&_.m(n,null),b(n,u),h||(a=et(c=ut.call(null,s)),h=!0)},p(p,f){e=p,f&2&&o!==(o=e[6]+"")&&fe(r,o),f&2&&i!==(i="/conversations/"+e[6])&&v(s,"href",i),e[3][e[6]]?_?_.p(e,f):(_=qe(e),_.c(),_.m(n,u)):_&&(_.d(1),_=null),f&6&&Te(n,"current",e[6]===e[2])},d(p){p&&R(n),_&&_.d(),h=!1,a()}}}function nn(t){let e,n,s,o,r,i,c,l=[],u=new Map,h,a,_=t[1];const p=f=>f[6];for(let f=0;f<_.length;f+=1){let d=Ke(t,_,f),m=p(d);u.set(m,l[f]=Be(m,d))}return{c(){e=w("div"),n=w("h3"),n.textContent="Contacts",s=N(),o=w("form"),r=w("input"),i=N(),c=w("ul");for(let f=0;f<l.length;f+=1)l[f].c();v(n,"class","svelte-ah7idb"),v(r,"placeholder","Add Contact"),v(c,"class","svelte-ah7idb"),v(e,"class","svelte-ah7idb")},m(f,d){M(f,e,d),b(e,n),b(e,s),b(e,o),b(o,r),le(r,t[0]),b(e,i),b(e,c);for(let m=0;m<l.length;m+=1)l[m].m(c,null);h||(a=[re(r,"input",t[5]),re(o,"submit",tt(t[4]))],h=!0)},p(f,[d]){d&1&&r.value!==f[0]&&le(r,f[0]),d&14&&(_=f[1],l=st(l,d,p,1,f,_,u,c,wt,Be,null,Ke))},i:E,o:E,d(f){f&&R(e);for(let d=0;d<l.length;d+=1)l[d].d();h=!1,U(a)}}}function sn(t,e,n){let s,o,r;A(t,Ne,u=>n(1,s=u)),A(t,ae,u=>n(2,o=u)),A(t,Xt,u=>n(3,r=u));let i="";function c(u){ft(i)&&(rt(`/conversations/${i}`),n(0,i=""))}function l(){i=this.value,n(0,i)}return[i,s,o,r,c,l]}class on extends F{constructor(e){super(),B(this,e,sn,nn,H,{})}}function rn(t){let e,n,s,o,r,i,c,l,u,h,a,_,p,f,d;return h=new on({}),{c(){e=w("nav"),n=w("h1"),n.textContent="PRISM",s=N(),o=w("h2"),r=q("Logged in as "),i=w("span"),i.textContent=`${ue}`,c=N(),l=w("hr"),u=N(),D(h.$$.fragment),a=N(),_=w("a"),_.textContent="Help",v(n,"class","svelte-1gcinxk"),v(i,"class","nobreak"),v(o,"class","svelte-1gcinxk"),v(l,"class","svelte-1gcinxk"),v(_,"href","/"),v(_,"class","svelte-1gcinxk"),v(e,"class","svelte-1gcinxk")},m(m,O){M(m,e,O),b(e,n),b(e,s),b(e,o),b(o,r),b(o,i),b(e,c),b(e,l),b(e,u),$(h,e,null),b(e,a),b(e,_),p=!0,f||(d=et(ut.call(null,_)),f=!0)},p:E,i(m){p||(C(h.$$.fragment,m),p=!0)},o(m){j(h.$$.fragment,m),p=!1},d(m){m&&R(e),I(h),f=!1,d()}}}class ln extends F{constructor(e){super(),B(this,e,null,rn,H,{})}}function cn(t){let e,n,s,o,r,i;return{c(){e=w("li"),n=w("p"),s=q(t[1]),o=N(),r=w("time"),r.textContent=`${t[2].toLocaleString()}`,v(n,"class","svelte-hajyoz"),v(r,"class","svelte-hajyoz"),v(e,"class",i=Me(t[0]===ue?"self":"other")+" svelte-hajyoz")},m(c,l){M(c,e,l),b(e,n),b(n,s),b(e,o),b(e,r)},p(c,[l]){l&2&&fe(s,c[1]),l&1&&i!==(i=Me(c[0]===ue?"self":"other")+" svelte-hajyoz")&&v(e,"class",i)},i:E,o:E,d(c){c&&R(e)}}}function un(t,e,n){let s;A(t,Se,a=>n(6,s=a));let{sender:o}=e,{timestamp:r}=e,{message:i}=e,{nonce:c}=e,{receive_time:l=null}=e;const u=new Date((l|r)*1e3);function h(){c in s||Ze(Se,s={...s,[c]:1},s)}return Oe(h),t.$$set=a=>{"sender"in a&&n(0,o=a.sender),"timestamp"in a&&n(3,r=a.timestamp),"message"in a&&n(1,i=a.message),"nonce"in a&&n(4,c=a.nonce),"receive_time"in a&&n(5,l=a.receive_time)},[o,i,u,r,c,l]}class an extends F{constructor(e){super(),B(this,e,un,cn,H,{sender:0,timestamp:3,message:1,nonce:4,receive_time:5})}}function Fe(t,e,n){const s=t.slice();return s[12]=e[n],s}function Ye(t,e){let n,s,o;const r=[e[12]];let i={};for(let c=0;c<r.length;c+=1)i=V(i,r[c]);return s=new an({props:i}),{key:t,first:null,c(){n=X(),D(s.$$.fragment),this.first=n},m(c,l){M(c,n,l),$(s,c,l),o=!0},p(c,l){e=c;const u=l&16?ot(r,[ye(e[12])]):{};s.$set(u)},i(c){o||(C(s.$$.fragment,c),o=!0)},o(c){j(s.$$.fragment,c),o=!1},d(c){c&&R(n),I(s,c)}}}function fn(t){let e,n,s,o,r,i,c,l,u,h,a=[],_=new Map,p,f,d,m,O,T,L=t[4];const k=y=>y[12].nonce;for(let y=0;y<L.length;y+=1){let g=Fe(t,L,y),S=k(g);_.set(S,a[y]=Ye(S,g))}return{c(){e=w("div"),n=w("h1"),s=w("span"),s.textContent="Conversation with",o=N(),r=w("span"),i=q(t[0]),c=N(),l=w("ul"),u=w("span"),h=N();for(let y=0;y<a.length;y+=1)a[y].c();p=N(),f=w("form"),d=w("input"),v(s,"class","quiet svelte-pgnkvj"),v(r,"class","nobreak svelte-pgnkvj"),v(n,"class","svelte-pgnkvj"),v(u,"class","dummy svelte-pgnkvj"),v(l,"class","svelte-pgnkvj"),v(d,"placeholder","Quick, say something smart!"),v(d,"class","svelte-pgnkvj"),v(f,"action","#"),v(f,"class","svelte-pgnkvj"),v(e,"class","svelte-pgnkvj")},m(y,g){M(y,e,g),b(e,n),b(n,s),b(n,o),b(n,r),b(r,i),b(e,c),b(e,l),b(l,u),b(l,h);for(let S=0;S<a.length;S+=1)a[S].m(l,null);t[6](l),b(e,p),b(e,f),b(f,d),le(d,t[1]),t[8](d),m=!0,O||(T=[re(d,"input",t[7]),re(f,"submit",tt(t[5]))],O=!0)},p(y,[g]){(!m||g&1)&&fe(i,y[0]),g&16&&(L=y[4],Z(),a=st(a,g,k,1,y,L,_,l,St,Ye,null,Fe),ee()),g&2&&d.value!==y[1]&&le(d,y[1])},i(y){if(!m){for(let g=0;g<L.length;g+=1)C(a[g]);m=!0}},o(y){for(let g=0;g<a.length;g+=1)j(a[g]);m=!1},d(y){y&&R(e);for(let g=0;g<a.length;g+=1)a[g].d();t[6](null),t[8](null),O=!1,U(T)}}}function dn(t,e,n){let s,o;A(t,ae,d=>n(10,s=d)),A(t,en,d=>n(4,o=d));let{contact:r}=e,i="",c,l,u;async function h(d){i.length!=0&&(await Vt("/send",{address:r,message:i}),n(1,i=""),a())}function a(){ft(r),Ze(ae,s=r,s),c.focus(),n(3,l.scrollTop=l.scrollHeight,l)}Oe(a),mt(()=>{u=l&&l.offsetHeight+l.scrollTop>l.scrollHeight-20}),gt(()=>{u&&l.scrollTo(0,l.scrollHeight)});function _(d){ie[d?"unshift":"push"](()=>{l=d,n(3,l)})}function p(){i=this.value,n(1,i)}function f(d){ie[d?"unshift":"push"](()=>{c=d,n(2,c)})}return t.$$set=d=>{"contact"in d&&n(0,r=d.contact)},[r,i,c,l,o,h,_,p,f]}class _n extends F{constructor(e){super(),B(this,e,dn,fn,H,{contact:0})}}function Ge(t){let e,n;return e=new _n({props:{contact:t[0].contact}}),{c(){D(e.$$.fragment)},m(s,o){$(e,s,o),n=!0},p(s,o){const r={};o&1&&(r.contact=s[0].contact),e.$set(r)},i(s){n||(C(e.$$.fragment,s),n=!0)},o(s){j(e.$$.fragment,s),n=!1},d(s){I(e,s)}}}function hn(t){let e=t[0].contact,n,s,o=Ge(t);return{c(){o.c(),n=X()},m(r,i){o.m(r,i),M(r,n,i),s=!0},p(r,i){i&1&&H(e,e=r[0].contact)?(Z(),j(o,1,1,E),ee(),o=Ge(r),o.c(),C(o,1),o.m(n.parentNode,n)):o.p(r,i)},i(r){s||(C(o),s=!0)},o(r){j(o),s=!1},d(r){r&&R(n),o.d(r)}}}function pn(t){let e;return{c(){e=w("p"),e.textContent='Click a name on the left or enter a name in the "Add Contact" field to start a new conversation.'},m(n,s){M(n,e,s)},p:E,d(n){n&&R(e)}}}function mn(t){let e,n,s,o,r,i,c;return e=new ln({}),o=new He({props:{path:"/conversations/:contact",$$slots:{default:[hn,({params:l})=>({0:l}),({params:l})=>l?1:0]},$$scope:{ctx:t}}}),i=new He({props:{path:"/",$$slots:{default:[pn]},$$scope:{ctx:t}}}),{c(){D(e.$$.fragment),n=N(),s=w("main"),D(o.$$.fragment),r=N(),D(i.$$.fragment),v(s,"class","svelte-w4s87")},m(l,u){$(e,l,u),M(l,n,u),M(l,s,u),$(o,s,null),b(s,r),$(i,s,null),c=!0},p(l,u){const h={};u&3&&(h.$$scope={dirty:u,ctx:l}),o.$set(h);const a={};u&2&&(a.$$scope={dirty:u,ctx:l}),i.$set(a)},i(l){c||(C(e.$$.fragment,l),C(o.$$.fragment,l),C(i.$$.fragment,l),c=!0)},o(l){j(e.$$.fragment,l),j(o.$$.fragment,l),j(i.$$.fragment,l),c=!1},d(l){I(e,l),l&&R(n),l&&R(s),I(o),I(i)}}}function gn(t){let e,n;return e=new qt({props:{$$slots:{default:[mn]},$$scope:{ctx:t}}}),{c(){D(e.$$.fragment)},m(s,o){$(e,s,o),n=!0},p(s,[o]){const r={};o&2&&(r.$$scope={dirty:o,ctx:s}),e.$set(r)},i(s){n||(C(e.$$.fragment,s),n=!0)},o(s){j(e.$$.fragment,s),n=!1},d(s){I(e,s)}}}class yn extends F{constructor(e){super(),B(this,e,null,gn,H,{})}}new yn({target:document.body});