/** Read-only gateway capability probe; never loaded by production planners. */
import {appendFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import type {ExtensionAPI} from '@earendil-works/pi-coding-agent';
export default function (pi: ExtensionAPI): void {
  pi.on('before_provider_request', event => {
    if (pi.getActiveTools().length !== 0 || !event.payload || typeof event.payload !== 'object' || Array.isArray(event.payload)) return;
    const schemaFormat = {type:'json_schema',json_schema:{name:'frozen_citation_selection',strict:true,schema:{
      type:'object',properties:{evidence:{type:'array',minItems:0,maxItems:8,items:{type:'object',properties:{
        ref:{type:'string'},endRef:{type:'string'}},required:['ref'],additionalProperties:false}}},required:['evidence'],additionalProperties:false,
    }}};
    const mode = process.env.PI_SCHEMA_DIAGNOSTIC_MODE;
    if (mode !== 'json-object' && mode !== 'json-schema') throw new Error('Unknown isolated diagnostic mode');
    const response_format = mode === 'json-schema' ? schemaFormat : {type:'json_object'};
    const request = {...event.payload,response_format};
    appendFileSync(process.env.PI_SCHEMA_DIAGNOSTIC_WIRE!,JSON.stringify({mode,responseFormat:response_format,payloadSha256:createHash('sha256').update(JSON.stringify(request)).digest('hex')})+'\n',{mode:0o600});
    return request;
  });
}
