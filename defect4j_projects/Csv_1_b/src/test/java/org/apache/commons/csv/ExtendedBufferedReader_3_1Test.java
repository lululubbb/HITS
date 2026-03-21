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

class ExtendedBufferedReader_3_1Test {

    private ExtendedBufferedReader extendedBufferedReader;

    @BeforeEach
    void setUp() {
        Reader dummyReader = new Reader() {
            @Override
            public int read(char[] cbuf, int off, int len) throws IOException {
                return -1;
            }

            @Override
            public void close() throws IOException {
            }
        };
        extendedBufferedReader = new ExtendedBufferedReader(dummyReader);
    }

    @Test
    @Timeout(8000)
    void testReadAgainInitialValue() throws Exception {
        Method readAgainMethod = ExtendedBufferedReader.class.getDeclaredMethod("readAgain");
        readAgainMethod.setAccessible(true);
        int result = (int) readAgainMethod.invoke(extendedBufferedReader);
        assertEquals(ExtendedBufferedReader.UNDEFINED, result);
    }

    @Test
    @Timeout(8000)
    void testReadAgainAfterSettingLastChar() throws Exception {
        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        lastCharField.setInt(extendedBufferedReader, 42);

        Method readAgainMethod = ExtendedBufferedReader.class.getDeclaredMethod("readAgain");
        readAgainMethod.setAccessible(true);
        int result = (int) readAgainMethod.invoke(extendedBufferedReader);
        assertEquals(42, result);
    }

    @Test
    @Timeout(8000)
    void testReadAgainAfterSettingLastCharToEndOfStream() throws Exception {
        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        lastCharField.setInt(extendedBufferedReader, ExtendedBufferedReader.END_OF_STREAM);

        Method readAgainMethod = ExtendedBufferedReader.class.getDeclaredMethod("readAgain");
        readAgainMethod.setAccessible(true);
        int result = (int) readAgainMethod.invoke(extendedBufferedReader);
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, result);
    }
}