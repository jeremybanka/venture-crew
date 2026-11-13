import fs from 'node:fs';
import path from 'node:path';
import { RigSpecSchema } from '@openrig/cli/daemon/dist/domain/rigspec-schema.js';
import { validateAgentSpec } from '@openrig/cli/daemon/dist/domain/agent-manifest.js';
const root = path.resolve(import.meta.dirname, '..');
const rig=JSON.parse(fs.readFileSync(path.join(root,'rig.yaml'),'utf8'));
const agent=JSON.parse(fs.readFileSync(path.join(root,'agents/crew/agent.yaml'),'utf8'));
let failed=false;
for(const [name,result] of [['rig',RigSpecSchema.validate(rig)],['agent',validateAgentSpec(agent)]]) {
 console.log(name,JSON.stringify(result,null,2));
 if(result.valid===false || result.errors?.length) failed=true;
}
if(failed)process.exit(1);
console.log('Pinned OpenRig schema validation passed; this does not launch a daemon or prove native hook enforcement.');
