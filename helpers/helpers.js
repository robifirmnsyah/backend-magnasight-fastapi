/**
 * Generate Unique ID
 * @param {string} prefix - Prefix untuk ID
 * @returns {string} Unique ID
 */
function generateUniqueId(prefix) {
    return `${prefix}-${Math.random().toString(36).substr(2, 8).toUpperCase()}`;
  }
  
  module.exports = { generateUniqueId };
  