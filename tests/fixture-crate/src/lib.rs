//! Fixture crate for the `jamshidhq/actions` self-test.

/// Add two numbers.
///
/// ```
/// assert_eq!(jamshidhq_actions_fixture::add(2, 3), 5);
/// ```
pub fn add(a: u64, b: u64) -> u64 {
    a + b
}

/// Double a number. Only built with the `extra` feature.
#[cfg(feature = "extra")]
pub fn double(a: u64) -> u64 {
    add(a, a)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn adds() {
        assert_eq!(add(1, 1), 2);
    }

    #[cfg(feature = "extra")]
    #[test]
    fn doubles() {
        assert_eq!(double(4), 8);
    }
}
