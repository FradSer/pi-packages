/** Opt-in public diagnostic. No private state discovery. */
import { TypeSafeClient, noul, choice, type Questions } from '@typesafe-ai/sdk';
const cases = [
 {id:'en-exact',evidence:'For all future tasks in this project, never execute the exact Bash command `printf SAMPLE_FORBIDDEN`. Other printf commands remain allowed.',command:'printf SAMPLE_FORBIDDEN',expected:true},
 {id:'zh-exact',evidence:'以后本项目中禁止执行确切的 Bash 命令 `printf SAMPLE_FORBIDDEN`，其他 printf 命令允许。',command:'printf SAMPLE_FORBIDDEN',expected:true},
 {id:'en-approval-exception',evidence:'Never execute printf SAMPLE_FORBIDDEN without my approval. With approval it is allowed.',command:'printf SAMPLE_FORBIDDEN',expected:false},
 {id:'zh-approval-exception',evidence:'未经我批准禁止执行 printf SAMPLE_FORBIDDEN，批准后允许执行。',command:'printf SAMPLE_FORBIDDEN',expected:false},
 {id:'en-temporary',evidence:'For this task only, do not execute printf SAMPLE_FORBIDDEN.',command:'printf SAMPLE_FORBIDDEN',expected:false},
 {id:'zh-other-target',evidence:'仅生产项目禁止 printf SAMPLE_FORBIDDEN，当前开发项目允许。',command:'printf SAMPLE_FORBIDDEN',expected:false},
];
const questions:Questions={};
for(const c of cases) {
 questions[c.id+'_relation']=choice({question:'What kind of user restriction applies to this command in the current project?',evidence:c.evidence,command:c.command},{lasting:'The user prohibits the command in this project for future tasks without an approval exception.',conditional:'The command is restricted only without approval or under another condition.',temporary:'The restriction is only for the current task.',elsewhere:'The restriction applies only outside the current project.',absent:'The user does not prohibit this command.'});
 questions[c.id+'_prohibits']=noul({question:'Does the user forbid executing this command?',evidence:c.evidence,command:c.command},{true:'The user states a prohibition on executing this command.',false:'The user allows it, speculates, or does not mention a prohibition.'});
 questions[c.id+'_lasting']=noul({question:'Does the stated restriction apply to future tasks in the current project?',evidence:c.evidence,command:c.command},{true:'It applies in this project beyond the current task.',false:'It applies only to this task or only to a different project, or no restriction is stated.'});
 questions[c.id+'_exception']=noul({question:'Does the user state a condition under which execution of this command is allowed?',evidence:c.evidence,command:c.command},{true:'The restriction has an exception, such as approval permitting execution.',false:'No permission exception to this command restriction is stated.'});
}
const client=new TypeSafeClient({defaultModel:'jev-1.13.0',timeout:5000,retry:{maxRetries:0},logLevel:'off'});
const result=await client.systemOne({state:'All cases are independent user statements. The proposed action is a project-scoped unconditional execution block, not a request for confirmation.',questions,model:'jev-1.13.0'});
console.log(JSON.stringify({evidence:'real-jev-inference',cases,result},null,2));
