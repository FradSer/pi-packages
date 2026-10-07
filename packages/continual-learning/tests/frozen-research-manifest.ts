/** Research only: bind samples and code to bytes captured before any paid call. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
const hash=(bytes:Buffer)=>createHash('sha256').update(bytes).digest('hex');
export async function readFrozenResearchManifest<T extends {codeHashes:Record<string,string>}>(file:URL):Promise<{value:T;sha256:string;verify():Promise<void>}> {
 const bytes=await fs.readFile(file),sha256=hash(bytes);
 const value=JSON.parse(bytes.toString('utf8')) as T;
 if(!value||typeof value!=='object'||!value.codeHashes||typeof value.codeHashes!=='object'||Array.isArray(value.codeHashes)
  ||Object.values(value.codeHashes).some(d=>typeof d!=='string'||! /^[a-f0-9]{64}$/.test(d)))throw new Error('Invalid frozen research manifest');
 const codeHashes={...value.codeHashes};
 const verify=async()=>{
  if(hash(await fs.readFile(file))!==sha256)throw new Error('Frozen research manifest changed');
  for(const [relative,digest]of Object.entries(codeHashes))if(hash(await fs.readFile(new URL(relative,file)))!==digest)throw new Error('Frozen research source changed');
 };
 await verify();return {value,sha256,verify};
}
