local osc52_copy = require("vim.ui.clipboard.osc52").copy("+")
local cached_selection = { {}, "v" }

local function copy(lines, regtype)
  cached_selection = { vim.deepcopy(lines), regtype }
  osc52_copy(lines)
end

local function paste()
  return cached_selection
end

-- OSC 52 reads are commonly blocked and would pause Neovim for 10 seconds.
-- Cache yanks locally for `p`; use the terminal paste action for remote text.
vim.g.clipboard = {
  name = "OSC 52 (copy only)",
  copy = {
    ["+"] = copy,
    ["*"] = copy,
  },
  paste = {
    ["+"] = paste,
    ["*"] = paste,
  },
}

-- LazyVim clears 'clipboard' during startup and restores its SSH-safe default
-- on VeryLazy. Re-enable unnamedplus after that deferred reset.
vim.opt.clipboard:append("unnamedplus")
vim.api.nvim_create_autocmd("User", {
  pattern = "VeryLazy",
  once = true,
  callback = function()
    vim.opt.clipboard:append("unnamedplus")
  end,
})
