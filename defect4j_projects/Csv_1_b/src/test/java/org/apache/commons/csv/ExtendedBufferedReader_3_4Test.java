package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Field;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_3_4Test {

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
    void testReadAgainWithDefaultValue() throws NoSuchMethodException, InvocationTargetException, IllegalAccessException {
        Method readAgainMethod = ExtendedBufferedReader.class.getDeclaredMethod("readAgain");
        readAgainMethod.setAccessible(true);

        // Initially lastChar is UNDEFINED (-2)
        int result = (int) readAgainMethod.invoke(extendedBufferedReader);
        assertEquals(-2, result);
    }

    @Test
    @Timeout(8000)
    void testReadAgainWithCustomLastChar() throws NoSuchMethodException, IllegalAccessException, InvocationTargetException, NoSuchFieldException {
        // Set lastChar to a specific value using reflection
        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        lastCharField.setInt(extendedBufferedReader, 100);

        Method readAgainMethod = ExtendedBufferedReader.class.getDeclaredMethod("readAgain");
        readAgainMethod.setAccessible(true);

        int result = (int) readAgainMethod.invoke(extendedBufferedReader);
        assertEquals(100, result);
    }
}