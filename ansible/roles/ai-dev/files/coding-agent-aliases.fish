function codex --wraps=codex --description "alias codex codex --dangerously-bypass-approvals-and-sandbox"
    command codex --dangerously-bypass-approvals-and-sandbox $argv
end

function claude --wraps=claude --description "alias claude claude --dangerously-skip-permissions"
    command claude --dangerously-skip-permissions $argv
end
