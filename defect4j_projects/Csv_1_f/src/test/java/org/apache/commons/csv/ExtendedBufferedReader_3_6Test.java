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

class ExtendedBufferedReader_3_6Test {

    private ExtendedBufferedReader extendedBufferedReader;

    @BeforeEach
    void setUp() {
        Reader reader = new Reader() {
            @Override
            public int read(char[] cbuf, int off, int len) throws IOException {
                return -1; // simulate end of stream
            }

            @Override
            public void close() throws IOException {
                // no-op
            }
        };
        extendedBufferedReader = new ExtendedBufferedReader(reader);
    }

    @Test
    @Timeout(8000)
    void testReadAgain_whenLastCharIsUndefined() throws Exception {
        // Use reflection to set private field lastChar to UNDEFINED
        setLastCharField(ExtendedBufferedReader.UNDEFINED);
        int result = invokeReadAgain();
        assertEquals(ExtendedBufferedReader.UNDEFINED, result);
    }

    @Test
    @Timeout(8000)
    void testReadAgain_whenLastCharIsEndOfStream() throws Exception {
        setLastCharField(ExtendedBufferedReader.END_OF_STREAM);
        int result = invokeReadAgain();
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, result);
    }

    @Test
    @Timeout(8000)
    void testReadAgain_whenLastCharIsPositive() throws Exception {
        int testChar = 65; // 'A'
        setLastCharField(testChar);
        int result = invokeReadAgain();
        assertEquals(testChar, result);
    }

    private void setLastCharField(int value) throws Exception {
        Field field = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        field.setAccessible(true);
        field.setInt(extendedBufferedReader, value);
    }

    private int invokeReadAgain() throws Exception {
        Method method = ExtendedBufferedReader.class.getDeclaredMethod("readAgain");
        method.setAccessible(true);
        return (int) method.invoke(extendedBufferedReader);
    }
}