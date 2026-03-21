package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

class ExtendedBufferedReader_3_2Test {

    private ExtendedBufferedReader extendedBufferedReader;

    @BeforeEach
    void setUp() {
        Reader mockReader = Mockito.mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader) {
            // Override read() to avoid IOException during tests
            @Override
            public int read() throws IOException {
                return -1;
            }
        };
    }

    @Test
    @Timeout(8000)
    void testReadAgainInitialValue() throws Exception {
        // Use reflection to access private field lastChar
        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);

        // Initially lastChar = UNDEFINED (-2)
        int result = invokeReadAgain();
        assertEquals(ExtendedBufferedReader.UNDEFINED, result);

        // Set lastChar to END_OF_STREAM (-1) and test
        lastCharField.setInt(extendedBufferedReader, ExtendedBufferedReader.END_OF_STREAM);
        result = invokeReadAgain();
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, result);

        // Set lastChar to arbitrary value and test
        lastCharField.setInt(extendedBufferedReader, 42);
        result = invokeReadAgain();
        assertEquals(42, result);
    }

    private int invokeReadAgain() throws Exception {
        Method readAgainMethod = ExtendedBufferedReader.class.getDeclaredMethod("readAgain");
        readAgainMethod.setAccessible(true);
        return (int) readAgainMethod.invoke(extendedBufferedReader);
    }
}