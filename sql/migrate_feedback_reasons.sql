-- Feedback granular opcional para beta MVP.
-- Compatible con filas existentes: like/dislike siguen funcionando sin reason.

ALTER TABLE user_feedback
ADD COLUMN IF NOT EXISTS reason TEXT;

ALTER TABLE user_feedback
ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_user_feedback_reason ON user_feedback(reason);
