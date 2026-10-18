import test from 'node:test';
import assert from 'node:assert/strict';
import {isWelcomeGreeting,welcomeText} from '../src/welcome.js';
test('welcome accepts greetings with accents, case, whitespace and punctuation',()=>{
 for(const text of ['hola','HOLA','¡Hola!','  buenas  ','inicio','menú','MENÚ','buenos días','buenas   tardes','buenas noches'])assert.equal(isWelcomeGreeting(text),true,text);
});
test('welcome does not capture purchases, support or unrelated conversations',()=>{
 for(const text of ['/comprar netflix','/soporte','/menu','hola mi contraseña es privada','quiero netflix','','a'.repeat(100),null])assert.equal(isWelcomeGreeting(text),false);
 for(const command of ['/catalogo','/pedidos','/soporte'])assert.ok(welcomeText.includes(command));
 assert.ok(welcomeText.includes('Verificación manual'));
});
